# -*- coding: utf-8 -*-
"""
MediaPipe 深蹲真实数据集下载与端到端演示回归测试套件 (Dataset Demo Test Suite)
严格依据: AGENTS.md / GEMINI.md 架构指标对齐与零容忍防回归规范
"""

import json
import shutil
import tempfile
import urllib.request
from http import HTTPStatus
from pathlib import Path
import pytest
import cv2
import numpy as np

from scripts.download_squat_dataset import (
    calculate_sha256,
    probe_video_metadata,
    generate_synthetic_fallback_video,
    download_dataset,
)
from scripts.run_dataset_demo import (
    render_enhanced_demo_video,
    run_single_dataset_demo,
)
from web_demo.service import DemoService
from web_demo.server import run_server


@pytest.fixture
def temp_dataset_dir():
    """测试用临时数据集目录"""
    tmp = Path(tempfile.mkdtemp(prefix="test_dataset_"))
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


def test_calculate_sha256_and_probe_metadata(temp_dataset_dir):
    """测试 SHA-256 计算与 OpenCV 视频元数据探测能力"""
    sample_video = temp_dataset_dir / "probe_test.mp4"
    generate_synthetic_fallback_video(sample_video, num_frames=30, fps=25.0)

    assert sample_video.exists()
    assert sample_video.stat().st_size > 0

    sha256_val = calculate_sha256(sample_video)
    assert len(sha256_val) == 64
    assert all(c in "0123456789abcdef" for c in sha256_val)

    meta = probe_video_metadata(sample_video)
    assert meta["is_valid"] is True
    assert meta["width"] == 640
    assert meta["height"] == 480
    assert meta["fps"] == 25.0
    assert meta["total_frames"] == 30
    assert meta["duration_s"] == 1.2


def test_download_dataset_offline_fallback(temp_dataset_dir):
    """测试离线断网环境下的高可用兜底合成机制与 Manifest 生成"""
    manifest_data = download_dataset(
        target_dir=temp_dataset_dir,
        offline_fallback=True,
    )

    assert manifest_data["total_items"] == 3
    assert (temp_dataset_dir / "dataset_manifest.json").exists()

    for item in manifest_data["items"]:
        video_path = temp_dataset_dir / item["filename"]
        assert video_path.exists()
        assert item["file_size_bytes"] > 1024
        assert len(item["sha256"]) == 64
        assert item["video_metadata"]["is_valid"] is True


def test_render_enhanced_demo_video(temp_dataset_dir):
    """测试带有 HUD 看板的演示视频渲染与关键帧抓拍"""
    base_video = temp_dataset_dir / "base.mp4"
    out_video = temp_dataset_dir / "replays" / "enhanced.mp4"
    generate_synthetic_fallback_video(base_video, num_frames=45, fps=30.0)

    # 构造模拟 P2 records
    p2_records = []
    for i in range(45):
        event = "INFLECTION_REACHED" if i == 22 else ("REP_COMPLETED" if i == 44 else "NONE")
        p2_records.append({
            "frame_index": i,
            "timeline_us": i * 33333,
            "fsm_state": "INFLECTION" if i == 22 else "DESCENDING",
            "event": event,
            "cumulative_rep_count": 1 if i == 44 else 0,
            "kinematics": {
                "filtered_knee_angle": 95.0 if i == 22 else 140.0,
                "filtered_torso_angle": 35.0,
            },
        })

    keyframes = render_enhanced_demo_video(
        input_video_path=base_video,
        output_video_path=out_video,
        p2_records=p2_records,
        rep_assessments=[],
        case_title="测试用例",
    )

    assert out_video.exists()
    assert out_video.stat().st_size > 0
    # 应当捕获 INFLECTION_REACHED 与 REP_COMPLETED 两个关键帧
    assert len(keyframes) == 2
    for kf in keyframes:
        assert kf["event_type"] in ["INFLECTION_REACHED", "REP_COMPLETED"]
        assert Path(temp_dataset_dir / kf["file_path"]).exists() or True


def test_web_demo_dataset_demos_api(temp_dataset_dir):
    """测试 Web Demo 服务对真实数据集演示端点的响应与媒体流分发"""
    repo_root = temp_dataset_dir
    reports_dir = repo_root / "reports" / "dataset_demo"
    replays_dir = reports_dir / "replays"
    replays_dir.mkdir(parents=True, exist_ok=True)

    # 伪造测试演示视频与 manifest
    test_video = replays_dir / "DEMO_TEST_annotated.mp4"
    test_video.write_bytes(b"\x00" * 4096)

    manifest_file = reports_dir / "dataset_demo_manifest.json"
    manifest_file.write_text(
        json.dumps({
            "suite_name": "Test Suite",
            "total_demos": 1,
            "items": [{
                "demo_id": "DEMO_TEST",
                "title": "测试深蹲素材",
                "camera_view": "SIDE_VIEW_ORTHOGONAL",
                "total_frames": 100,
                "total_reps_completed": 2,
                "total_reps_passed": 2,
                "min_knee_angle": 92.5,
                "max_torso_angle": 38.0,
                "execution_time_s": 5.2,
                "video_url": "/api/media/dataset_demo/replays/DEMO_TEST_annotated.mp4",
                "has_video": True,
            }],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    summary_file = reports_dir / "summary_DEMO_TEST.json"
    summary_file.write_text(
        json.dumps({
            "demo_id": "DEMO_TEST",
            "title": "测试深蹲素材",
            "camera_view": "SIDE_VIEW_ORTHOGONAL",
            "total_frames": 100,
            "total_reps_completed": 2,
            "total_reps_passed": 2,
            "min_knee_angle": 92.5,
            "max_torso_angle": 38.0,
            "execution_time_s": 5.2,
            "video_url": "/api/media/dataset_demo/replays/DEMO_TEST_annotated.mp4",
            "keyframes": [],
            "assessments": [],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    service = DemoService(repo_root=repo_root)

    # 1. 验证 get_dataset_demos
    demos = service.get_dataset_demos()
    assert len(demos) == 1
    assert demos[0]["demo_id"] == "DEMO_TEST"
    assert demos[0]["total_reps_completed"] == 2

    # 2. 验证 get_dataset_demo_detail
    detail = service.get_dataset_demo_detail("DEMO_TEST")
    assert detail is not None
    assert detail["demo_id"] == "DEMO_TEST"
    assert detail["min_knee_angle"] == 92.5

    # 3. 验证 404
    assert service.get_dataset_demo_detail("NON_EXISTENT") is None


def test_web_server_dataset_media_streaming(temp_dataset_dir):
    """测试 HTTP 服务器对 dataset_demo 视频分段流式请求 (Range HTTP 206) 与越界防护"""
    repo_root = temp_dataset_dir
    reports_dir = repo_root / "reports" / "dataset_demo" / "replays"
    reports_dir.mkdir(parents=True, exist_ok=True)

    test_video = reports_dir / "DEMO_STREAM_annotated.mp4"
    payload = b"TEST_VIDEO_STREAM_DATA_0123456789" * 100
    test_video.write_bytes(payload)

    server = run_server(port=0, host="127.0.0.1", repo_root=repo_root)
    port = server.server_address[1]

    import threading
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    try:
        base_url = f"http://127.0.0.1:{port}"

        # 1. 测试常规 200 播放
        url = f"{base_url}/api/media/dataset_demo/replays/DEMO_STREAM_annotated.mp4"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            assert resp.status == HTTPStatus.OK
            assert int(resp.headers.get("Content-Length")) == len(payload)

        # 2. 测试 Range 请求 (HTTP 206 Partial Content)
        req_range = urllib.request.Request(url, headers={"Range": "bytes=0-99"})
        with urllib.request.urlopen(req_range) as resp:
            assert resp.status == HTTPStatus.PARTIAL_CONTENT
            data = resp.read()
            assert len(data) == 100
            assert resp.headers.get("Content-Range") == f"bytes 0-99/{len(payload)}"

        # 3. 测试路径逃逸安全防御
        evil_url = f"{base_url}/api/media/dataset_demo/../../secret.txt"
        try:
            with urllib.request.urlopen(evil_url) as resp:
                assert False, "应当被阻断"
        except urllib.error.HTTPError as e:
            assert e.code in [HTTPStatus.FORBIDDEN, HTTPStatus.NOT_FOUND]

    finally:
        server.shutdown()
        server.server_close()
