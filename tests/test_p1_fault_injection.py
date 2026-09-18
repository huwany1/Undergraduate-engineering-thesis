# -*- coding: utf-8 -*-
"""
P1 故障注入与异常熔断闭合测试
验证在输入异常、缺少 Permit、模型缺失及写出损坏等场景下，
系统安全熔断闭合，绝不生成 SUCCESS 凭据，绝不伪造成功
"""

import tempfile
import shutil
from pathlib import Path
import pytest
import cv2
import numpy as np

from p1_pipeline.runner import PipelineRunner
from p1_pipeline.input_probe import InputProbeError
from p1_pipeline.engine.tasks_adapter import MediaPipeTasksPoseEngine, PoseEngineError
from p1_pipeline.engine.mock_adapter import DeterministicMockPoseEngine
from p1_pipeline.contracts import ReasonCode


@pytest.fixture
def fault_env():
    temp_dir = Path(tempfile.mkdtemp(prefix="p1_fault_test_"))
    video_path = temp_dir / "valid_video.mp4"
    output_root = temp_dir / "output"

    # 生成 10 帧有效测试视频
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 25.0, (320, 240))
    for _ in range(10):
        writer.write(np.zeros((240, 320, 3), dtype=np.uint8))
    writer.release()

    valid_permit = {
        "baseline_id": "P0-SQUAT-SIDE-OFFLINE-v1.0",
        "sample_id": "SMP-001",
        "source_video_id": "VID-01",
        "runtime_permit": {
            "processing_permit_id": "PRM-VALID",
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
        "valid_permit": valid_permit,
    }

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_fault_injection_invalid_permits(fault_env):
    """测试各种非法或被撤销 Permit 均被精准拒绝"""
    runner = PipelineRunner(output_root=fault_env["output_root"], engine=DeterministicMockPoseEngine())

    # 1. 撤销状态
    revoked_permit = dict(fault_env["valid_permit"])
    revoked_permit["runtime_permit"] = {"processing_permit_id": "PRM-1", "disposal_status": "REVOKED"}
    with pytest.raises(InputProbeError) as exc_info:
        runner.run(fault_env["video_path"], revoked_permit)
    assert exc_info.value.reason_code == ReasonCode.P0_PERMIT_INVALID

    # 2. 准入质量未通过
    rejected_permit = dict(fault_env["valid_permit"])
    rejected_permit["admission_status"] = {"quality_status": "REJECTED"}
    with pytest.raises(InputProbeError) as exc_info:
        runner.run(fault_env["video_path"], rejected_permit)
    assert exc_info.value.reason_code == ReasonCode.P0_PERMIT_INVALID

    # 3. baseline_id 缺失
    bad_baseline = dict(fault_env["valid_permit"])
    bad_baseline["baseline_id"] = "UNKNOWN_BASELINE"
    with pytest.raises(InputProbeError) as exc_info:
        runner.run(fault_env["video_path"], bad_baseline)
    assert exc_info.value.reason_code == ReasonCode.P0_PERMIT_INVALID

    # 确认无任何产物生成
    assert not fault_env["output_root"].exists() or len(list(fault_env["output_root"].glob("*"))) == 0


def test_fault_injection_missing_video(fault_env):
    """测试视频路径不存在时报错 INPUT_NOT_FOUND"""
    runner = PipelineRunner(output_root=fault_env["output_root"], engine=DeterministicMockPoseEngine())
    with pytest.raises(InputProbeError) as exc_info:
        runner.run(fault_env["temp_dir"] / "non_existent.mp4", fault_env["valid_permit"])
    assert exc_info.value.reason_code == ReasonCode.INPUT_NOT_FOUND


def test_fault_injection_missing_model_asset(fault_env):
    """测试 MediaPipe Tasks 模型文件不存在时报 MODEL_ASSET_MISSING"""
    engine = MediaPipeTasksPoseEngine(model_path="models/not_exist.task")
    runner = PipelineRunner(output_root=fault_env["output_root"], engine=engine)

    with pytest.raises(PoseEngineError) as exc_info:
        runner.run(fault_env["video_path"], fault_env["valid_permit"])

    assert exc_info.value.reason_code == ReasonCode.MODEL_ASSET_MISSING

    # 确认没有 SUCCESS 凭据生成
    success_markers = list(fault_env["output_root"].glob("**/SUCCESS"))
    assert len(success_markers) == 0


def test_fault_injection_model_hash_mismatch(fault_env):
    """测试模型文件哈希不匹配时报 MODEL_HASH_MISMATCH"""
    fake_model = fault_env["temp_dir"] / "dummy.task"
    fake_model.write_text("corrupted content", encoding="utf-8")

    engine = MediaPipeTasksPoseEngine(
        model_path=str(fake_model),
        expected_sha256="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    runner = PipelineRunner(output_root=fault_env["output_root"], engine=engine)

    with pytest.raises(PoseEngineError) as exc_info:
        runner.run(fault_env["video_path"], fault_env["valid_permit"])

    assert exc_info.value.reason_code == ReasonCode.MODEL_HASH_MISMATCH

    success_markers = list(fault_env["output_root"].glob("**/SUCCESS"))
    assert len(success_markers) == 0
