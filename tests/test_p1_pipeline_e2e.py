# -*- coding: utf-8 -*-
"""
P1 端到端流水线集成测试
"""

import json
import csv
import shutil
import tempfile
from pathlib import Path
import pytest
import cv2
import numpy as np

from p1_pipeline.runner import PipelineRunner
from p1_pipeline.engine.mock_adapter import DeterministicMockPoseEngine
from p1_pipeline.contracts import TimeBasis


@pytest.fixture
def test_env():
    temp_dir = Path(tempfile.mkdtemp(prefix="p1_test_e2e_"))
    video_path = temp_dir / "input_squat.mp4"
    output_root = temp_dir / "output"

    # 生成 20 帧合成测试视频
    width, height, fps = 320, 240, 25.0
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video_path), fourcc, fps, (width, height))
    for i in range(20):
        img = np.zeros((height, width, 3), dtype=np.uint8)
        img[:, :] = (i * 10 % 255, 120, 80)
        cv2.putText(img, f"Frame {i}", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        writer.write(img)
    writer.release()

    permit_data = {
        "baseline_id": "P0-SQUAT-SIDE-OFFLINE-v1.0",
        "sample_id": "SMP-E2E-001",
        "source_video_id": "VID-REC-01",
        "runtime_permit": {
            "processing_permit_id": "PRM-E2E-001-A7",
            "disposal_status": "ACTIVE_HOLD",
        },
        "admission_status": {
            "quality_status": "ADMITTED",
        },
    }

    yield {
        "temp_dir": temp_dir,
        "video_path": video_path,
        "output_root": output_root,
        "permit_data": permit_data,
        "num_frames": 20,
        "width": width,
        "height": height,
    }

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_pipeline_e2e_complete_success(test_env):
    """验证 P1 完整单向流水线正常运行、五计数完全对齐、成品齐备"""
    engine = DeterministicMockPoseEngine(simulate_side="LEFT")
    runner = PipelineRunner(
        output_root=test_env["output_root"],
        engine=engine,
        time_basis=TimeBasis.DERIVED_CFR_NONRELEASE,
    )

    report = runner.run(
        video_path=test_env["video_path"],
        permit_data=test_env["permit_data"],
    )

    # 1. 验证五计数与重开核验
    assert report.is_valid is True
    assert report.decoded_count == test_env["num_frames"]
    assert report.inferred_count == test_env["num_frames"]
    assert report.rendered_count == test_env["num_frames"]
    assert report.written_count == test_env["num_frames"]
    assert report.sidecar_count == test_env["num_frames"]
    assert report.verified_video_frames == test_env["num_frames"]

    # 2. 验证成品包产物
    published_dirs = list(test_env["output_root"].glob("input_squat-*"))
    assert len(published_dirs) == 1
    target_dir = published_dirs[0]

    overlay_mp4 = target_dir / "overlay.mp4"
    keypoints_jsonl = target_dir / "keypoints.jsonl"
    frames_csv = target_dir / "frames.csv"
    manifest_json = target_dir / "manifest.json"
    validation_json = target_dir / "validation.json"
    success_marker = target_dir / "SUCCESS"

    assert overlay_mp4.exists()
    assert keypoints_jsonl.exists()
    assert frames_csv.exists()
    assert manifest_json.exists()
    assert validation_json.exists()
    assert success_marker.exists()

    # 3. 验证 keypoints.jsonl
    lines = keypoints_jsonl.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == test_env["num_frames"]
    for idx, line in enumerate(lines):
        record = json.loads(line)
        assert record["frame_index"] == idx
        assert len(record["pose"]["landmarks_2d"]) == 33
        assert record["quality"]["overlay_status"] in ["DRAWABLE", "SIDE_CHANGED", "REQUIRED_JOINT_INVALID"]

    # 4. 验证 frames.csv
    with open(frames_csv, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        assert "frame_index" in header
        csv_rows = list(reader)
        assert len(csv_rows) == test_env["num_frames"]

    # 5. 验证 manifest.json
    with open(manifest_json, "r", encoding="utf-8") as f:
        m = json.load(f)
        assert m["baseline_id"] == "P0-SQUAT-SIDE-OFFLINE-v1.0"
        assert m["processing_permit_id"] == "PRM-E2E-001-A7"
        assert m["counts"]["decoded_count"] == test_env["num_frames"]

    # 6. 重开生成的视频，验证可正常解码且尺寸完全一致
    cap = cv2.VideoCapture(str(overlay_mp4))
    assert cap.isOpened()
    assert int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) == test_env["width"]
    assert int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) == test_env["height"]
    read_count = 0
    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            break
        read_count += 1
    cap.release()
    assert read_count == test_env["num_frames"]
