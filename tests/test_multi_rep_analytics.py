# -*- coding: utf-8 -*-
"""
连续动作切片与多维统计分析自动化测试套件 (Multi-Rep Analytics Test Suite)
严格依据: AGENTS.md / GEMINI.md 测试驱动与防回归规则
"""

import json
from pathlib import Path
import pytest

from p2_temporal.contracts import RepetitionRecord
from p2_temporal.analytics.group_analytics import (
    MultiRepAnalyticsEngine,
    ConsistencyScoreResult,
    DepthDecayResult,
    TempoAnalysisResult,
    SingleRepSlice,
    MultiRepSummary,
)
from p3_rules.contracts import RepetitionAssessment, AssessmentStatus, RuleViolation, Severity


def create_mock_rep(
    rep_id: int,
    start_ms: float,
    bottom_ms: float,
    end_ms: float,
    min_knee: float,
    max_torso: float,
    status: str = "COMPLETED",
) -> RepetitionRecord:
    """构造用于测试的时序动作切片实体"""
    duration = end_ms - start_ms
    desc_duration = bottom_ms - start_ms
    asc_duration = end_ms - bottom_ms

    return RepetitionRecord(
        rep_id=rep_id,
        is_valid=True,
        status=status,
        start_frame=int(start_ms / 33.33),
        bottom_frame=int(bottom_ms / 33.33),
        end_frame=int(end_ms / 33.33),
        start_timeline_us=int(start_ms * 1000),
        bottom_timeline_us=int(bottom_ms * 1000),
        end_timeline_us=int(end_ms * 1000),
        duration_ms=duration,
        descending_duration_ms=desc_duration,
        ascending_duration_ms=asc_duration,
        min_knee_angle=min_knee,
        max_torso_lean_angle=max_torso,
        reason_codes=["NORMAL"],
    )


def test_multi_rep_empty_boundary():
    """测试 N=0 空边界场景下的优雅处理与零异常"""
    summary = MultiRepAnalyticsEngine.analyze([])
    assert summary.total_completed_reps == 0
    assert summary.passed_reps == 0
    assert summary.pass_rate_pct == 0.0
    assert summary.consistency.score == 0.0
    assert summary.consistency.grade == "NO_DATA"
    assert summary.depth_decay.status == "NO_DATA"
    assert summary.depth_decay.slope_deg_per_rep == 0.0
    assert len(summary.slices) == 0

    d = summary.to_dict()
    assert isinstance(d, dict)
    assert d["total_completed_reps"] == 0


def test_multi_rep_single_rep_boundary():
    """测试 N=1 单次深蹲边界场景（无法计算多轮离散，基准一致性评为 100 分，斜率为 0）"""
    rep = create_mock_rep(1, 1000, 2500, 3800, 85.0, 32.0)
    summary = MultiRepAnalyticsEngine.analyze([rep])

    assert summary.total_completed_reps == 1
    assert summary.passed_reps == 1
    assert summary.pass_rate_pct == 100.0
    assert summary.consistency.score == 100.0
    assert summary.consistency.grade == "SINGLE_REP"
    assert summary.depth_decay.status == "SINGLE_REP"
    assert summary.depth_decay.slope_deg_per_rep == 0.0
    assert summary.depth_decay.progression == [85.0]
    assert len(summary.slices) == 1
    assert summary.slices[0].rep_id == 1
    assert summary.slices[0].tempo_str == "1.5s - 0.0s - 1.3s"


def test_multi_rep_perfect_consistency_set():
    """测试 N=5 极高一致性深蹲组（深度标准差接近 0，得分 >= 95）"""
    reps = [
        create_mock_rep(1, 0, 1500, 3000, 75.0, 30.0),
        create_mock_rep(2, 4000, 5500, 7000, 75.2, 30.1),
        create_mock_rep(3, 8000, 9500, 11000, 74.9, 29.9),
        create_mock_rep(4, 12000, 13500, 15000, 75.1, 30.2),
        create_mock_rep(5, 16000, 17500, 19000, 75.0, 30.0),
    ]
    summary = MultiRepAnalyticsEngine.analyze(reps)

    assert summary.total_completed_reps == 5
    assert summary.consistency.score >= 95.0
    assert summary.consistency.grade == "EXCELLENT"
    assert summary.consistency.knee_std < 0.5
    assert summary.depth_decay.status == "STABLE"
    assert abs(summary.depth_decay.slope_deg_per_rep) < 0.2


def test_multi_rep_fatigue_decay_detection():
    """测试连续动作下蹲深度衰减趋势与疲劳识别 (以真实 DEMO_02 数据模拟: 62.7° -> 68.8°)"""
    reps = [
        create_mock_rep(1, 1000, 2520, 3800, 62.7, 53.5),
        create_mock_rep(2, 5000, 6360, 7640, 64.5, 52.1),
        create_mock_rep(3, 9000, 10320, 11760, 67.3, 54.2),
        create_mock_rep(4, 13000, 14320, 15760, 66.6, 58.1),
        create_mock_rep(5, 17000, 18360, 19920, 67.5, 57.1),
        create_mock_rep(6, 21000, 22320, 23720, 68.8, 56.9),
    ]
    summary = MultiRepAnalyticsEngine.analyze(reps)

    assert summary.total_completed_reps == 6
    assert summary.depth_decay.status == "FATIGUE_DETECTED"
    assert summary.depth_decay.slope_deg_per_rep > 0.8
    assert summary.depth_decay.total_delta_deg == pytest.approx(6.1, abs=0.1)
    assert "衰减" in summary.depth_decay.description
    assert summary.depth_decay.progression == [62.7, 64.5, 67.3, 66.6, 67.5, 68.8]


def test_multi_rep_warmup_improved_detection():
    """测试热身充分逐渐加深场景 (95° -> 75°)"""
    reps = [
        create_mock_rep(1, 0, 1500, 3000, 95.0, 30.0),
        create_mock_rep(2, 4000, 5500, 7000, 88.0, 30.0),
        create_mock_rep(3, 8000, 9500, 11000, 80.0, 30.0),
        create_mock_rep(4, 12000, 13500, 15000, 75.0, 30.0),
    ]
    summary = MultiRepAnalyticsEngine.analyze(reps)

    assert summary.total_completed_reps == 4
    assert summary.depth_decay.status == "WARM_UP_IMPROVED"
    assert summary.depth_decay.slope_deg_per_rep < -0.8
    assert summary.depth_decay.total_delta_deg == -20.0
    assert "加深" in summary.depth_decay.description


def test_multi_rep_tempo_analysis():
    """测试离心/向心收缩节奏剖析与失控下蹲预警"""
    # 离心过快组 (<0.8s 自由落体式下蹲)
    fast_fall_reps = [
        create_mock_rep(1, 0, 500, 2000, 80.0, 30.0),
        create_mock_rep(2, 3000, 3600, 5000, 80.0, 30.0),
    ]
    fast_summary = MultiRepAnalyticsEngine.analyze(fast_fall_reps)
    assert fast_summary.tempo.avg_descending_s < 0.8
    assert "下蹲离心速度偏快" in fast_summary.tempo.pacing_feedback

    # 控速良好组 (离心 1.8s, 向心 1.2s)
    good_reps = [
        create_mock_rep(1, 0, 1800, 3000, 80.0, 30.0),
        create_mock_rep(2, 4000, 5800, 7000, 80.0, 30.0),
    ]
    good_summary = MultiRepAnalyticsEngine.analyze(good_reps)
    assert good_summary.tempo.avg_descending_s >= 1.5
    assert good_summary.tempo.eccentric_concentric_ratio >= 1.0
    assert "离心下蹲充分受控" in good_summary.tempo.pacing_feedback


def test_multi_rep_with_p3_assessments_integration():
    """测试时序切片与 P3 要点评估实体融合生成 SingleRepSlice"""
    reps = [
        create_mock_rep(1, 0, 1500, 3000, 80.0, 30.0),
        create_mock_rep(2, 4000, 5500, 7000, 110.0, 55.0),
    ]

    ass1 = RepetitionAssessment(
        rep_id=1,
        overall_status=AssessmentStatus.ACCEPTABLE,
        primary_reason_code="ACCEPTABLE",
        violations=[],
        summary_feedback="动作规范良好",
    )
    ass2 = RepetitionAssessment(
        rep_id=2,
        overall_status=AssessmentStatus.NEEDS_IMPROVEMENT,
        primary_reason_code="INSUFFICIENT_DEPTH",
        violations=[
            RuleViolation(
                rule_id="R-DEPTH-001",
                reason_code="INSUFFICIENT_DEPTH",
                severity=Severity.WARNING_SEVERE,
                feedback_text="深度不足",
            )
        ],
        summary_feedback="下蹲深度未达标且前倾偏大",
    )

    summary = MultiRepAnalyticsEngine.analyze(reps, assessments=[ass1, ass2])
    assert summary.total_completed_reps == 2
    assert summary.passed_reps == 1
    assert summary.pass_rate_pct == 50.0

    s1 = summary.slices[0]
    assert s1.rep_id == 1
    assert s1.overall_status == "ACCEPTABLE"
    assert s1.feedback_text == "动作规范良好"

    s2 = summary.slices[1]
    assert s2.rep_id == 2
    assert s2.overall_status == "NEEDS_IMPROVEMENT"
    assert s2.primary_reason_code == "INSUFFICIENT_DEPTH"
    assert len(s2.violations) == 1
    assert s2.violations[0]["rule_id"] == "R-DEPTH-001"


def test_multi_rep_real_dataset_demo_02_integration():
    """测试开源真实数据集 DEMO_02 (6 次深蹲) 的切片与宏观统计全真加载"""
    manifest_path = Path("data/S2_derived_features/dataset_demo_runs/sample_squat_deep-7d0d2490/p2_temporal/repetitions_manifest.json")
    if not manifest_path.exists():
        pytest.skip("DEMO_02 本地派生数据未生成")

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    reps = [
        RepetitionRecord(
            rep_id=r["rep_id"],
            is_valid=r["is_valid"],
            status=r["status"],
            start_frame=r["start_frame"],
            bottom_frame=r["bottom_frame"],
            end_frame=r["end_frame"],
            start_timeline_us=r["start_timeline_us"],
            bottom_timeline_us=r["bottom_timeline_us"],
            end_timeline_us=r["end_timeline_us"],
            duration_ms=r["duration_ms"],
            descending_duration_ms=r["descending_duration_ms"],
            ascending_duration_ms=r["ascending_duration_ms"],
            min_knee_angle=r["min_knee_angle"],
            max_torso_lean_angle=r["max_torso_lean_angle"],
            reason_codes=r.get("reason_codes", []),
        )
        for r in data["repetitions"]
    ]

    summary = MultiRepAnalyticsEngine.analyze(reps)
    assert summary.total_completed_reps == 6
    assert len(summary.slices) == 6
    # 验证膝角衰减趋势从 62.7° 衰减到 68.8°
    assert summary.depth_decay.status == "FATIGUE_DETECTED"
    assert summary.depth_decay.slope_deg_per_rep > 0.5
    assert summary.depth_decay.progression[0] == pytest.approx(62.71, abs=0.1)
    assert summary.depth_decay.progression[-1] == pytest.approx(65.38, abs=0.1)
    # 验证切片各段起止时间严格单调
    for s in summary.slices:
        assert s.start_time_s < s.bottom_time_s < s.end_time_s
        assert s.duration_s > 1.5
