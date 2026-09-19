# -*- coding: utf-8 -*-
"""
R-ASYM-001 动作双侧不对称规则单元测试
依据: AGENTS.md 规范与维度二实施方案
"""

import math
import pytest
from p2_temporal.contracts import RepetitionRecord
from p3_rules.contracts import (
    AsymmetryRuleConfig,
    Severity,
    AssessmentReasonCode,
)
from p3_rules.evaluators.asymmetry_evaluator import BilateralAsymmetryEvaluator
from p3_rules.feedback.sanitizer import SanitizerGate


def make_rep(diff_deg=None):
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
        extended_metrics={"max_bilateral_diff_deg": diff_deg},
    )


def test_asymmetry_pass_symmetric():
    evaluator = BilateralAsymmetryEvaluator()
    rep = make_rep(diff_deg=6.5)
    res = evaluator.evaluate(rep)
    assert res is None


def test_asymmetry_unobservable_none():
    evaluator = BilateralAsymmetryEvaluator()
    rep = make_rep(diff_deg=None)
    res = evaluator.evaluate(rep)
    assert res is None


def test_asymmetry_fail_mild():
    evaluator = BilateralAsymmetryEvaluator()
    rep = make_rep(diff_deg=17.0)
    res = evaluator.evaluate(rep)
    assert res is not None
    assert res.rule_id == "R-ASYM-001"
    assert res.reason_code == AssessmentReasonCode.BILATERAL_ASYMMETRY.value
    assert res.severity == Severity.WARNING_MILD
    assert res.evidence is not None
    assert res.evidence.feature_name == "max_bilateral_diff_deg"
    assert res.evidence.measured_value == 17.0
    assert "双腿屈曲角度略有不对称" in res.feedback_text
    SanitizerGate().validate(res.feedback_text)


def test_asymmetry_fail_severe():
    evaluator = BilateralAsymmetryEvaluator()
    rep = make_rep(diff_deg=25.0)
    res = evaluator.evaluate(rep)
    assert res is not None
    assert res.severity == Severity.WARNING_SEVERE
    assert "显著的动作双侧不对称" in res.feedback_text
    SanitizerGate().validate(res.feedback_text)


def test_asymmetry_nan_protection():
    evaluator = BilateralAsymmetryEvaluator()
    rep = make_rep(diff_deg=float("nan"))
    res = evaluator.evaluate(rep)
    assert res is not None
    assert res.severity == Severity.REJECT
    assert res.reason_code == AssessmentReasonCode.FEATURE_DEGENERATE.value
