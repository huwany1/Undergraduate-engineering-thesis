# -*- coding: utf-8 -*-
"""
R-VALGUS-001 膝关节内扣规则单元测试
依据: AGENTS.md 规范与维度二实施方案
"""

import math
import pytest
from p2_temporal.contracts import RepetitionRecord
from p3_rules.contracts import (
    ValgusRuleConfig,
    Severity,
    AssessmentReasonCode,
)
from p3_rules.evaluators.valgus_evaluator import KneeValgusEvaluator
from p3_rules.feedback.sanitizer import SanitizerGate


def make_rep(valgus_ratio=None, bottom_frame=50, bottom_us=1666666):
    return RepetitionRecord(
        rep_id=1,
        is_valid=True,
        status="COMPLETED",
        start_frame=10,
        bottom_frame=bottom_frame,
        end_frame=90,
        start_timeline_us=333333,
        bottom_timeline_us=bottom_us,
        end_timeline_us=3000000,
        duration_ms=2666.7,
        descending_duration_ms=1333.3,
        ascending_duration_ms=1333.4,
        min_knee_angle=90.0,
        max_torso_lean_angle=30.0,
        extended_metrics={"min_valgus_ratio": valgus_ratio},
    )


def test_valgus_pass_normal():
    evaluator = KneeValgusEvaluator()
    rep = make_rep(valgus_ratio=0.95)
    res = evaluator.evaluate(rep)
    assert res is None


def test_valgus_unobservable_none():
    evaluator = KneeValgusEvaluator()
    rep = make_rep(valgus_ratio=None)
    res = evaluator.evaluate(rep)
    assert res is None


def test_valgus_fail_mild():
    evaluator = KneeValgusEvaluator()
    rep = make_rep(valgus_ratio=0.80)
    res = evaluator.evaluate(rep)
    assert res is not None
    assert res.rule_id == "R-VALGUS-001"
    assert res.reason_code == AssessmentReasonCode.KNEE_VALGUS.value
    assert res.severity == Severity.WARNING_MILD
    assert res.evidence is not None
    assert res.evidence.feature_name == "min_valgus_ratio"
    assert res.evidence.measured_value == 0.80
    assert "略有内扣" in res.feedback_text
    SanitizerGate().validate(res.feedback_text)


def test_valgus_fail_severe():
    evaluator = KneeValgusEvaluator()
    rep = make_rep(valgus_ratio=0.65)
    res = evaluator.evaluate(rep)
    assert res is not None
    assert res.severity == Severity.WARNING_SEVERE
    assert "明显的膝关节内扣" in res.feedback_text
    SanitizerGate().validate(res.feedback_text)


def test_valgus_nan_protection():
    evaluator = KneeValgusEvaluator()
    rep = make_rep(valgus_ratio=float("nan"))
    res = evaluator.evaluate(rep)
    assert res is not None
    assert res.severity == Severity.REJECT
    assert res.reason_code == AssessmentReasonCode.FEATURE_DEGENERATE.value
