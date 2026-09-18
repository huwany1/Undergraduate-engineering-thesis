# -*- coding: utf-8 -*-
"""
P3 自动化测试套件：端到端全链路动作评估与 Schema 验证测试
"""

import pytest
from p2_temporal.contracts import RepetitionRecord
from p3_rules.engine import SquatAssessmentEngine
from p3_rules.contracts import (
    AssessmentStatus,
    AssessmentReasonCode,
    RuleCardConfig,
)


def make_rep(
    rep_id: int,
    status: str = "COMPLETED",
    duration_ms: float = 2000.0,
    min_knee_angle: float = 85.0,
    max_torso_lean_angle: float = 30.0,
) -> RepetitionRecord:
    return RepetitionRecord(
        rep_id=rep_id,
        is_valid=(status == "COMPLETED"),
        status=status,
        start_frame=10,
        bottom_frame=35,
        end_frame=60,
        start_timeline_us=333333,
        bottom_timeline_us=1166666,
        end_timeline_us=2000000,
        duration_ms=duration_ms,
        descending_duration_ms=duration_ms / 2,
        ascending_duration_ms=duration_ms / 2,
        min_knee_angle=min_knee_angle,
        max_torso_lean_angle=max_torso_lean_angle,
        reason_codes=[],
    )


def test_p3_end_to_end_perfect_squat():
    engine = SquatAssessmentEngine()
    rep = make_rep(rep_id=1, min_knee_angle=88.0, max_torso_lean_angle=32.0)

    res = engine.evaluate_repetition(rep)

    assert res.rep_id == 1
    assert res.overall_status == AssessmentStatus.ACCEPTABLE
    assert res.primary_reason_code == AssessmentReasonCode.ACCEPTABLE.value
    assert len(res.violations) == 0
    assert "动作规范" in res.summary_feedback

    # 验证 Schema 序列化完整性
    d = res.to_dict()
    assert d["overall_status"] == "ACCEPTABLE"
    assert d["aggregation_policy_version"] == "AGGR-SQUAT-v1.0"
    assert isinstance(d["violations"], list)


def test_p3_end_to_end_shallow_squat():
    engine = SquatAssessmentEngine()
    rep = make_rep(rep_id=2, min_knee_angle=112.5, max_torso_lean_angle=30.0)

    res = engine.evaluate_repetition(rep)

    assert res.overall_status == AssessmentStatus.NEEDS_IMPROVEMENT
    assert res.primary_reason_code == AssessmentReasonCode.INSUFFICIENT_DEPTH.value
    assert len(res.violations) == 1
    assert res.violations[0].rule_id == "R-DEPTH-001"
    assert res.violations[0].evidence is not None
    assert res.violations[0].evidence.measured_value == pytest.approx(112.5, abs=0.01)
    assert "下蹲深度显著不足" in res.summary_feedback


def test_p3_end_to_end_excessive_lean_squat():
    engine = SquatAssessmentEngine()
    rep = make_rep(rep_id=3, min_knee_angle=86.0, max_torso_lean_angle=54.2)

    res = engine.evaluate_repetition(rep)

    assert res.overall_status == AssessmentStatus.NEEDS_IMPROVEMENT
    assert res.primary_reason_code == AssessmentReasonCode.EXCESSIVE_TORSO_LEAN.value
    assert len(res.violations) == 1
    assert res.violations[0].rule_id == "R-LEAN-001"
    assert res.violations[0].evidence.measured_value == pytest.approx(54.2, abs=0.01)
    assert "躯干过度前倾" in res.summary_feedback


def test_p3_end_to_end_dual_defect_squat():
    engine = SquatAssessmentEngine()
    rep = make_rep(rep_id=4, min_knee_angle=114.0, max_torso_lean_angle=52.0)

    res = engine.evaluate_repetition(rep)

    assert res.overall_status == AssessmentStatus.NEEDS_IMPROVEMENT
    assert len(res.violations) == 2
    # 双方均严重超标，按 rule_id 字典序排列 (R-DEPTH-001 优先于 R-LEAN-001)
    assert res.violations[0].rule_id == "R-DEPTH-001"
    assert res.violations[1].rule_id == "R-LEAN-001"
    assert "下蹲深度显著不足" in res.summary_feedback
    assert "躯干过度前倾" in res.summary_feedback


def test_p3_end_to_end_reproducibility_hash():
    """验证相同输入产生 100% 确定性输出字典"""
    engine = SquatAssessmentEngine()
    rep = make_rep(rep_id=5, min_knee_angle=105.0, max_torso_lean_angle=49.0)

    res1 = engine.evaluate_repetition(rep).to_dict()
    res2 = engine.evaluate_repetition(rep).to_dict()

    assert res1 == res2


def test_p3_evaluate_all_batch():
    engine = SquatAssessmentEngine()
    reps = [
        make_rep(rep_id=1, min_knee_angle=85.0, max_torso_lean_angle=30.0),
        make_rep(rep_id=2, min_knee_angle=110.0, max_torso_lean_angle=30.0),
        make_rep(rep_id=3, status="ABORTED", min_knee_angle=120.0),
    ]

    assessments = engine.evaluate_all(reps)
    assert len(assessments) == 3
    assert assessments[0].overall_status == AssessmentStatus.ACCEPTABLE
    assert assessments[1].overall_status == AssessmentStatus.NEEDS_IMPROVEMENT
    assert assessments[2].overall_status == AssessmentStatus.NOT_EVALUATED
