# -*- coding: utf-8 -*-
"""
P3 自动化测试套件：R-LEAN-001 躯干前倾代理规则测试
"""

import pytest
from p2_temporal.contracts import RepetitionRecord
from p3_rules.evaluators.lean_evaluator import TorsoLeanEvaluator
from p3_rules.contracts import (
    AssessmentReasonCode,
    Severity,
    LeanRuleConfig,
)


def make_rep(max_torso_lean_angle: float, bottom_frame: int = 32) -> RepetitionRecord:
    return RepetitionRecord(
        rep_id=1,
        is_valid=True,
        status="COMPLETED",
        start_frame=10,
        bottom_frame=bottom_frame,
        end_frame=55,
        start_timeline_us=333333,
        bottom_timeline_us=1066666,
        end_timeline_us=1833333,
        duration_ms=1500.0,
        descending_duration_ms=733.3,
        ascending_duration_ms=766.7,
        min_knee_angle=88.0,
        max_torso_lean_angle=max_torso_lean_angle,
        reason_codes=[],
    )


def test_lean_rule_pass_upright():
    evaluator = TorsoLeanEvaluator(LeanRuleConfig(threshold_deg=45.0))
    rep = make_rep(max_torso_lean_angle=28.5)
    violation = evaluator.evaluate(rep)
    assert violation is None, "躯干倾角 28.5° 直立稳定，不应触发违规"


def test_lean_rule_pass_boundary():
    evaluator = TorsoLeanEvaluator(LeanRuleConfig(threshold_deg=45.0))
    rep = make_rep(max_torso_lean_angle=45.0)
    violation = evaluator.evaluate(rep)
    assert violation is None, "躯干倾角刚好等于 45° 时判定合格"


def test_lean_rule_fail_mild():
    evaluator = TorsoLeanEvaluator(LeanRuleConfig(threshold_deg=45.0, tolerance_deg=3.0))
    rep = make_rep(max_torso_lean_angle=46.8)
    violation = evaluator.evaluate(rep)
    assert violation is not None
    assert violation.reason_code == AssessmentReasonCode.EXCESSIVE_TORSO_LEAN.value
    assert violation.severity == Severity.WARNING_MILD
    assert "躯干略有前倾" in violation.feedback_text
    assert violation.evidence.delta_value == pytest.approx(1.8, abs=0.01)


def test_lean_rule_fail_severe():
    evaluator = TorsoLeanEvaluator(LeanRuleConfig(threshold_deg=45.0, tolerance_deg=3.0))
    rep = make_rep(max_torso_lean_angle=58.3)
    violation = evaluator.evaluate(rep)
    assert violation is not None
    assert violation.reason_code == AssessmentReasonCode.EXCESSIVE_TORSO_LEAN.value
    assert violation.severity == Severity.WARNING_SEVERE
    assert "躯干过度前倾" in violation.feedback_text
    assert violation.evidence.delta_value == pytest.approx(13.3, abs=0.01)


def test_lean_rule_evidence_snapshot():
    evaluator = TorsoLeanEvaluator(LeanRuleConfig(threshold_deg=45.0))
    rep = make_rep(max_torso_lean_angle=52.1, bottom_frame=38)
    violation = evaluator.evaluate(rep)
    assert violation is not None
    ev = violation.evidence
    assert ev.feature_name == "max_torso_lean_angle"
    assert ev.measured_value == pytest.approx(52.1, abs=0.01)
    assert ev.threshold_value == 45.0
    assert ev.trigger_frame_index == 38
    assert ev.unit == "deg"


def test_lean_rule_nan_protection():
    evaluator = TorsoLeanEvaluator()
    rep = make_rep(max_torso_lean_angle=float("nan"))
    violation = evaluator.evaluate(rep)
    assert violation is not None
    assert violation.reason_code == AssessmentReasonCode.FEATURE_DEGENERATE.value
    assert violation.severity == Severity.REJECT
