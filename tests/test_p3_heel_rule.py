# -*- coding: utf-8 -*-
"""
R-HEEL-001 脚后跟离地规则单元测试
依据: AGENTS.md 规范与维度二实施方案
"""

import math
import pytest
from p2_temporal.contracts import RepetitionRecord
from p3_rules.contracts import (
    HeelLiftRuleConfig,
    Severity,
    AssessmentReasonCode,
)
from p3_rules.evaluators.heel_evaluator import HeelLiftEvaluator
from p3_rules.feedback.sanitizer import SanitizerGate


def make_rep(heel_lift_deg=0.0):
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
        extended_metrics={"max_heel_lift_deg": heel_lift_deg},
    )


def test_heel_pass_grounded():
    evaluator = HeelLiftEvaluator()
    rep = make_rep(heel_lift_deg=3.5)
    res = evaluator.evaluate(rep)
    assert res is None


def test_heel_fail_mild():
    evaluator = HeelLiftEvaluator()
    rep = make_rep(heel_lift_deg=14.0)
    res = evaluator.evaluate(rep)
    assert res is not None
    assert res.rule_id == "R-HEEL-001"
    assert res.reason_code == AssessmentReasonCode.HEEL_LIFT.value
    assert res.severity == Severity.WARNING_MILD
    assert res.evidence is not None
    assert res.evidence.feature_name == "max_heel_lift_deg"
    assert res.evidence.measured_value == 14.0
    assert "脚跟略有抬起" in res.feedback_text
    SanitizerGate().validate(res.feedback_text)


def test_heel_fail_severe():
    evaluator = HeelLiftEvaluator()
    rep = make_rep(heel_lift_deg=22.0)
    res = evaluator.evaluate(rep)
    assert res is not None
    assert res.severity == Severity.WARNING_SEVERE
    assert "明显的脚后跟离地" in res.feedback_text
    SanitizerGate().validate(res.feedback_text)


def test_heel_nan_protection():
    evaluator = HeelLiftEvaluator()
    rep = make_rep(heel_lift_deg=float("nan"))
    res = evaluator.evaluate(rep)
    assert res is not None
    assert res.severity == Severity.REJECT
    assert res.reason_code == AssessmentReasonCode.FEATURE_DEGENERATE.value
