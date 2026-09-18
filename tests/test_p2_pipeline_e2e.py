# -*- coding: utf-8 -*-
"""
P2 端到端完整时序闭环集成测试
验证消费 P1 产物后生成合规的 P2 Sidecar 与 Repetitions 清单
"""

import json
import pytest
from pathlib import Path
from p2_temporal.runner import P2TemporalPipeline


def make_p1_frame_record(frame_idx: int, knee_angle_deg: float, is_drawable: bool = True):
    """构造一条符合 P1 Sidecar 标准的测试帧记录"""
    import math

    # knee 位于 (0.5, 0.7)
    knee_x, knee_y = 0.5, 0.7
    # hip 垂直位于 knee 上方 0.2: (0.5, 0.5)
    hip_x, hip_y = 0.5, 0.5

    # 计算 ankle 坐标，使向量 (hip - knee) 与 (ankle - knee) 的夹角严格为 knee_angle_deg
    rad = math.radians(180.0 - knee_angle_deg)
    ankle_x = knee_x - 0.2 * math.sin(rad)
    ankle_y = knee_y + 0.2 * math.cos(rad)

    landmarks = [{"x": 0.5, "y": 0.5} for _ in range(33)]
    landmarks[11] = {"x": hip_x, "y": hip_y - 0.2}  # shoulder
    landmarks[23] = {"x": hip_x, "y": hip_y}        # hip
    landmarks[25] = {"x": knee_x, "y": knee_y}      # knee
    landmarks[27] = {"x": ankle_x, "y": ankle_y}    # ankle

    return {
        "run_id": "test-run-p2-e2e",
        "frame_index": frame_idx,
        "timeline_us": frame_idx * 33333,
        "pose_result": {
            "processing_status": "OK",
            "pose_status": "POSE_DETECTED",
            "landmarks_2d": landmarks,
        },
        "quality": {
            "overlay_status": "DRAWABLE" if is_drawable else "REQUIRED_JOINT_INVALID",
            "required_side": "LEFT",
        },
    }


def test_p2_pipeline_e2e_full(tmp_path: Path):
    """端到端验证 P2 时序分析：一次标准完整深蹲 + 一次半程深蹲"""
    p1_file = tmp_path / "p1_sidecar.jsonl"
    out_dir = tmp_path / "p2_out"

    # 生成 120 帧合成测试数据
    records = []
    # 阶段 1: 站立 (0-19 帧, 175度)
    for i in range(20):
        records.append(make_p1_frame_record(len(records), 175.0))

    # 阶段 2: 标准深蹲下蹲至 85度并起立 (20-69 帧)
    for i in range(25):
        ang = 175.0 - (175.0 - 85.0) * (i / 24.0)
        records.append(make_p1_frame_record(len(records), ang))
    for i in range(25):
        ang = 85.0 + (175.0 - 85.0) * (i / 24.0)
        records.append(make_p1_frame_record(len(records), ang))

    # 阶段 3: 中间站立 (70-79 帧, 175度)
    for i in range(10):
        records.append(make_p1_frame_record(len(records), 175.0))

    # 阶段 4: 半程深蹲蹲至 130度后提前起立 (80-109 帧)
    for i in range(15):
        ang = 175.0 - (175.0 - 130.0) * (i / 14.0)
        records.append(make_p1_frame_record(len(records), ang))
    for i in range(15):
        ang = 130.0 + (175.0 - 130.0) * (i / 14.0)
        records.append(make_p1_frame_record(len(records), ang))

    # 阶段 5: 最终站立 (110-119 帧, 175度)
    for i in range(10):
        records.append(make_p1_frame_record(len(records), 175.0))

    # 写入 mock p1 文件
    with open(p1_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    # 执行流水线
    pipeline = P2TemporalPipeline()
    summary = pipeline.run_from_p1_sidecar(
        p1_sidecar_path=str(p1_file),
        output_dir=str(out_dir),
        required_side="LEFT",
    )

    # 校验产物存在性
    assert (out_dir / "p2_sidecar.jsonl").exists()
    assert (out_dir / "repetitions_manifest.json").exists()
    assert (out_dir / "p2_summary.json").exists()

    # 校验产物数据
    assert summary["total_frames_processed"] == 120
    assert summary["cumulative_reps"] == 1
    assert summary["attempted_reps"] == 2
    assert summary["aborted_reps"] == 1

    with open(out_dir / "repetitions_manifest.json", "r", encoding="utf-8") as rf:
        manifest = json.load(rf)

    assert manifest["total_completed_reps"] == 1
    reps = manifest["repetitions"]
    assert len(reps) == 2

    # 第 1 次标准深蹲: 有效完成
    assert reps[0]["status"] == "COMPLETED"
    assert reps[0]["is_valid"] is True
    assert reps[0]["min_knee_angle"] <= 90.0

    # 第 2 次半程深蹲: 提前起立夭折
    assert reps[1]["status"] == "ABORTED"
    assert reps[1]["is_valid"] is False
