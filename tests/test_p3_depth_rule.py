# -*- coding: utf-8 -*-
"""
P3 自动化测试套件：R-DEPTH-001 下蹲深度代理规则测试
"""

import pytest
from p2_temporal.contracts import RepetitionRecord
from p3_rules.evaluators.depth_evaluator import SquatDepthEvaluator
from p3_rules.contracts import (
    AssessmentReasonCode,
    Severity,
    DepthRuleConfig,
)


def make_rep(min_knee_angle: float, bottom_frame: int = 35) -> RepetitionRecord:
    return RepetitionRecord(
        rep_id=1,
        is_valid=True,
        status="COMPLETED",
        start_frame=10,
        bottom_frame=bottom_frame,
        end_frame=60,
        start_timeline_us=333333,
        bottom_timeline_us=1166666,
        end_timeline_us=2000000,
        duration_ms=1666.7,
        descending_duration_ms=833.3,
        ascending_duration_ms=833.4,
        min_knee_angle=min_knee_angle,
        max_torso_lean_angle=30.0,
        reason_codes=[],
    )


def test_depth_rule_pass_deep_squat():
    evaluator = SquatDepthEvaluator(DepthRuleConfig(threshold_deg=100.0))
    rep = make_rep(min_knee_angle=85.0)
    violation = evaluator.evaluate(rep)
    assert violation is None, "膝角 85° 充分达标，不应触发违规"


def test_depth_rule_pass_boundary():
    evaluator = SquatDepthEvaluator(DepthRuleConfig(threshold_deg=100.0))
    rep = make_rep(min_knee_angle=100.0)
    violation = evaluator.evaluate(rep)
    assert violation is None, "膝角刚好等于阈值 100° 时判定合格"


def test_depth_rule_fail_mild():
    evaluator = SquatDepthEvaluator(DepthRuleConfig(threshold_deg=100.0, tolerance_deg=3.0))
    rep = make_rep(min_knee_angle=102.5)
    violation = evaluator.evaluate(rep)
    assert violation is not None
    assert violation.reason_code == AssessmentReasonCode.INSUFFICIENT_DEPTH.value
    assert violation.severity == Severity.WARNING_MILD
    assert "下蹲深度稍浅" in violation.feedback_text
    assert violation.evidence.delta_value == pytest.approx(2.5, abs=0.01)


def test_depth_rule_fail_severe():
    evaluator = SquatDepthEvaluator(DepthRuleConfig(threshold_deg=100.0, tolerance_deg=3.0))
    rep = make_rep(min_knee_angle=114.2)
    violation = evaluator.evaluate(rep)
    assert violation is not None
    assert violation.reason_code == AssessmentReasonCode.INSUFFICIENT_DEPTH.value
    assert violation.severity == Severity.WARNING_SEVERE
    assert "下蹲深度显著不足" in violation.feedback_text
    assert violation.evidence.delta_value == pytest.approx(14.2, abs=0.01)


def test_depth_rule_evidence_snapshot():
    evaluator = SquatDepthEvaluator(DepthRuleConfig(threshold_deg=100.0))
    rep = make_rep(min_knee_angle=108.45, bottom_frame=42)
    violation = evaluator.evaluate(rep)
    assert violation is not None
    ev = violation.evidence
    assert ev.feature_name == "min_knee_angle"
    assert ev.measured_value == pytest.approx(108.45, abs=0.01)
    assert ev.threshold_value == 100.0
    assert ev.trigger_frame_index == 42
    assert ev.unit == "deg"


def test_depth_rule_nan_protection():
    evaluator = SquatDepthEvaluator()
    rep = make_rep(min_knee_angle=float("nan"))
    violation = evaluator.evaluate(rep)
    assert violation is not None
    assert violation.reason_code == AssessmentReasonCode.FEATURE_DEGENERATE.value
    assert violation.severity == Severity.REJECT
