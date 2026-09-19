# -*- coding: utf-8 -*-
"""
实时骨架渲染数据契约、动态双角与递增计次时序自动化测试 (Real-time Skeleton & Telemetry Tests)
覆盖:
1. 在线分析流水线导出的 telemetry 包含 33 点归一化姿态骨骼坐标 (landmarks);
2. 业务适配层 DemoService 加载并持久化保留 landmarks 字段;
3. 遥测时序中 cumulative_rep_count 的非减递增性断言 (支持前端 0 -> 1 -> 2 实时计次);
4. 实时膝关节屈曲角与躯干前倾角时序字段完备性与有效性校验.
"""

import json
from pathlib import Path
import pytest

from web_demo.service import DemoService
from web_demo.analyzer import OnlineAnalysisManager, AnalysisTask, AnalysisTaskStatus


def test_service_load_telemetry_preserves_landmarks(tmp_path):
    """验证 DemoService._load_telemetry 能正确提取并保留 sidecar 中的 landmarks 数据"""
    service = DemoService(repo_root=tmp_path)
    service.sidecars_dir = tmp_path / "sidecars"
    service.sidecars_dir.mkdir(parents=True, exist_ok=True)

    fake_case_id = "TC_TEST_SKELETON"
    sidecar_file = service.sidecars_dir / f"{fake_case_id}_frames.jsonl"

    # 构造含 33 点骨骼数据的模拟时序帧
    sample_landmarks = [[round(i * 0.03, 4), round(i * 0.02, 4), 0.95] for i in range(33)]

    records = [
        {
            "frame_index": 0,
            "timeline_us": 0,
            "fsm_state": "STANDING",
            "cumulative_rep_count": 0,
            "event": "NONE",
            "kinematics": {
                "raw_knee_angle": 175.0,
                "filtered_knee_angle": 175.0,
                "raw_torso_angle": 10.0,
                "filtered_torso_angle": 10.0,
                "is_valid": True,
            },
            "landmarks": sample_landmarks,
        },
        {
            "frame_index": 1,
            "timeline_us": 33333,
            "fsm_state": "SQUATTING",
            "cumulative_rep_count": 0,
            "event": "NONE",
            "kinematics": {
                "raw_knee_angle": 120.0,
                "filtered_knee_angle": 120.0,
                "raw_torso_angle": 25.0,
                "filtered_torso_angle": 25.0,
                "is_valid": True,
            },
            "landmarks": sample_landmarks,
        },
        {
            "frame_index": 2,
            "timeline_us": 66666,
            "fsm_state": "STANDING",
            "cumulative_rep_count": 1,
            "event": "REP_COMPLETED",
            "kinematics": {
                "raw_knee_angle": 172.0,
                "filtered_knee_angle": 172.0,
                "raw_torso_angle": 12.0,
                "filtered_torso_angle": 12.0,
                "is_valid": True,
            },
            "landmarks": sample_landmarks,
        },
    ]

    with open(sidecar_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    telemetry = service._load_telemetry(fake_case_id)
    assert len(telemetry) == 3

    for pt in telemetry:
        assert "landmarks" in pt
        assert len(pt["landmarks"]) == 33
        # 验证每个关节点具备 [x, y, vis]
        assert len(pt["landmarks"][0]) == 3
        assert 0.0 <= pt["landmarks"][0][0] <= 1.0
        assert 0.0 <= pt["landmarks"][0][1] <= 1.0
        assert "knee_angle" in pt
        assert "torso_angle" in pt
        assert "count" in pt

    # 验证计次从 0 到 1 动态递增
    assert telemetry[0]["count"] == 0
    assert telemetry[1]["count"] == 0
    assert telemetry[2]["count"] == 1


def test_telemetry_incremental_rep_counting():
    """验证实际验证包或上传用例的时序遥测支持单调非递减的实时计次更新"""
    service = DemoService()
    cases = service.get_cases()
    assert len(cases) >= 5

    # 提取第 1 个标杆用例 TC_01_PERFECT_SQUAT 的真实遥测时序
    tc1_detail = service.get_case_detail("TC_01_PERFECT_SQUAT")
    assert tc1_detail is not None
    telemetry = tc1_detail.get("telemetry", [])
    assert len(telemetry) > 0

    # 验证首帧 count 为 0，随动作完成达到 1
    counts = [t["count"] for t in telemetry]
    assert counts[0] == 0
    assert counts[-1] == 1

    # 验证单调非减
    for i in range(1, len(counts)):
        assert counts[i] >= counts[i - 1]


def test_uploaded_case_detail_has_landmarks_and_angles(tmp_path):
    """验证用户上传分析详情中包含骨骼 landmarks 与实时双角数据"""
    service = DemoService(repo_root=tmp_path)
    manager = service.analysis_manager
    manager.summary_dir.mkdir(parents=True, exist_ok=True)

    fake_task_id = "up_skeleton123"
    fake_landmarks = [[0.5, 0.5, 0.99] for _ in range(33)]

    sample_summary = {
        "case_id": f"UPLOAD_{fake_task_id}",
        "task_id": fake_task_id,
        "case_name": "自定义深蹲测试",
        "description": "骨骼渲染测试视频",
        "actual_count": 1,
        "actual_status": "ACCEPTABLE",
        "actual_primary_reason": "NONE",
        "measured_min_knee_angle": 95.2,
        "measured_max_torso_angle": 28.6,
        "execution_time_ms": 1200.0,
        "summary_feedback": "动作规范",
        "has_video": True,
        "video_url": f"/api/media/uploaded/video/{fake_task_id}.mp4",
        "telemetry": [
            {
                "frame_index": 0,
                "time_s": 0.0,
                "knee_angle": 170.0,
                "raw_knee_angle": 170.0,
                "torso_angle": 10.0,
                "raw_torso_angle": 10.0,
                "fsm_state": "STANDING",
                "event": "NONE",
                "is_valid": True,
                "count": 0,
                "landmarks": fake_landmarks,
            },
            {
                "frame_index": 15,
                "time_s": 0.5,
                "knee_angle": 95.2,
                "raw_knee_angle": 95.2,
                "torso_angle": 28.6,
                "raw_torso_angle": 28.6,
                "fsm_state": "BOTTOM",
                "event": "INFLECTION_REACHED",
                "is_valid": True,
                "count": 0,
                "landmarks": fake_landmarks,
            },
            {
                "frame_index": 30,
                "time_s": 1.0,
                "knee_angle": 168.0,
                "raw_knee_angle": 168.0,
                "torso_angle": 11.0,
                "raw_torso_angle": 11.0,
                "fsm_state": "STANDING",
                "event": "REP_COMPLETED",
                "is_valid": True,
                "count": 1,
                "landmarks": fake_landmarks,
            },
        ],
        "keyframes": [],
    }

    # 写入测试 summary 文件
    summary_file = manager.summary_dir / f"{fake_task_id}_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(sample_summary, f)

    detail = service.get_uploaded_case_detail(f"UPLOAD_{fake_task_id}")
    assert detail is not None
    assert detail["case_id"] == f"UPLOAD_{fake_task_id}"
    assert len(detail["telemetry"]) == 3

    t_bottom = detail["telemetry"][1]
    assert t_bottom["knee_angle"] == 95.2
    assert t_bottom["torso_angle"] == 28.6
    assert t_bottom["fsm_state"] == "BOTTOM"
    assert len(t_bottom["landmarks"]) == 33


def test_real_uploaded_pipeline_exports_landmarks():
    """验证真实在线分析流水线生成的持久化 sidecar 与 summary 包含真实的 33 点姿态骨骼"""
    service = DemoService()
    summaries = list(service.analysis_manager.summary_dir.glob("up_*_summary.json"))
    if not summaries:
        pytest.skip("尚无在线分析历史记录，跳过真实文件校验")

    latest_summary = max(summaries, key=lambda p: p.stat().st_mtime)
    with open(latest_summary, "r", encoding="utf-8") as f:
        data = json.load(f)

    telemetry = data.get("telemetry", [])
    assert len(telemetry) > 0
    valid_frames = [t for t in telemetry if t.get("is_valid") and t.get("landmarks")]
    assert len(valid_frames) > 0, "在线分析导出的有效帧必须包含骨骼关键点"
    first_valid = valid_frames[0]
    assert len(first_valid["landmarks"]) == 33
    for pt in first_valid["landmarks"]:
        assert len(pt) == 3
        assert 0.0 <= pt[0] <= 1.0
        assert 0.0 <= pt[1] <= 1.0

