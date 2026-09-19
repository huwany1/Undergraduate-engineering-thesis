# -*- coding: utf-8 -*-
"""
R-PELVIC-001 骨盆翻转(臀部眨眼)规则单元测试
依据: AGENTS.md 规范与维度二实施方案
"""

import math
import pytest
from p2_temporal.contracts import RepetitionRecord
from p3_rules.contracts import (
    PelvicTiltRuleConfig,
    Severity,
    AssessmentReasonCode,
)
from p3_rules.evaluators.pelvic_evaluator import PelvicTiltEvaluator
from p3_rules.feedback.sanitizer import SanitizerGate


def make_rep(pelvic_tilt_deg=0.0):
    return RepetitionRecord(
        rep_id=1,
        is_valid=True,
        status="COMPLETED",
        start_frame=10,
        bottom_frame=50,
        end_frame=90,
        start_timeline_us=333333,
        bottom_timeline_us=1666666,
        end_timeline_us=3000000,
        duration_ms=2666.7,
        descending_duration_ms=1333.3,
        ascending_duration_ms=1333.4,
        min_knee_angle=90.0,
        max_torso_lean_angle=30.0,
        extended_metrics={"max_pelvic_tilt_deg": pelvic_tilt_deg},
    )


def test_pelvic_pass_stable():
    evaluator = PelvicTiltEvaluator()
    rep = make_rep(pelvic_tilt_deg=4.0)
    res = evaluator.evaluate(rep)
    assert res is None


def test_pelvic_fail_mild():
    evaluator = PelvicTiltEvaluator()
    rep = make_rep(pelvic_tilt_deg=12.0)
    res = evaluator.evaluate(rep)
    assert res is not None
    assert res.rule_id == "R-PELVIC-001"
    assert res.reason_code == AssessmentReasonCode.PELVIC_TILT.value
    assert res.severity == Severity.WARNING_MILD
    assert res.evidence is not None
    assert res.evidence.feature_name == "max_pelvic_tilt_deg"
    assert res.evidence.measured_value == 12.0
    assert "骨盆后倾翻转" in res.feedback_text
    SanitizerGate().validate(res.feedback_text)


def test_pelvic_fail_severe():
    evaluator = PelvicTiltEvaluator()
    rep = make_rep(pelvic_tilt_deg=18.0)
    res = evaluator.evaluate(rep)
    assert res is not None
    assert res.severity == Severity.WARNING_SEVERE
    assert "明显的骨盆后倾翻转" in res.feedback_text
    SanitizerGate().validate(res.feedback_text)


def test_pelvic_nan_protection():
    evaluator = PelvicTiltEvaluator()
    rep = make_rep(pelvic_tilt_deg=float("nan"))
    res = evaluator.evaluate(rep)
    assert res is not None
    assert res.severity == Severity.REJECT
    assert res.reason_code == AssessmentReasonCode.FEATURE_DEGENERATE.value
