# -*- coding: utf-8 -*-
"""
P3 自动化测试套件：R-CYCLE-001 周期完整性规则与准入门禁测试
"""

import pytest
from p2_temporal.contracts import RepetitionRecord
from p3_rules.evaluators.cycle_evaluator import CycleIntegrityEvaluator
from p3_rules.contracts import (
    AssessmentReasonCode,
    Severity,
    CycleRuleConfig,
)


def make_rep(
    rep_id: int = 1,
    is_valid: bool = True,
    status: str = "COMPLETED",
    duration_ms: float = 2000.0,
    min_knee_angle: float = 85.0,
    max_torso_lean_angle: float = 30.0,
) -> RepetitionRecord:
    return RepetitionRecord(
        rep_id=rep_id,
        is_valid=is_valid,
        status=status,
        start_frame=10,
        bottom_frame=30,
        end_frame=50,
        start_timeline_us=333333,
        bottom_timeline_us=1000000,
        end_timeline_us=1666666,
        duration_ms=duration_ms,
        descending_duration_ms=duration_ms / 2,
        ascending_duration_ms=duration_ms / 2,
        min_knee_angle=min_knee_angle,
        max_torso_lean_angle=max_torso_lean_angle,
        reason_codes=[],
    )


def test_cycle_rule_normal_completed():
    evaluator = CycleIntegrityEvaluator()
    rep = make_rep(status="COMPLETED", duration_ms=2500.0)
    violation = evaluator.evaluate(rep)
    assert violation is None, "正常周期应准入通过，无违规项"


def test_cycle_rule_aborted_incomplete():
    evaluator = CycleIntegrityEvaluator()
    rep = make_rep(status="ABORTED", is_valid=False, duration_ms=1200.0)
    violation = evaluator.evaluate(rep)
    assert violation is not None
    assert violation.reason_code == AssessmentReasonCode.INCOMPLETE_REP.value
    assert violation.severity == Severity.REJECT
    assert "未经历完整起蹲周期" in violation.feedback_text


def test_cycle_rule_too_fast_rejected():
    evaluator = CycleIntegrityEvaluator(CycleRuleConfig(min_duration_ms=800.0))
    rep = make_rep(status="COMPLETED", duration_ms=450.0)
    violation = evaluator.evaluate(rep)
    assert violation is not None
    assert violation.reason_code == AssessmentReasonCode.DISCARDED_TOO_FAST.value
    assert violation.severity == Severity.REJECT
    assert violation.evidence is not None
    assert violation.evidence.measured_value == 450.0
    assert violation.evidence.delta_value == -350.0
    assert "完成过快" in violation.feedback_text


def test_cycle_rule_timeout_rejected():
    evaluator = CycleIntegrityEvaluator(CycleRuleConfig(max_duration_ms=8000.0))
    rep = make_rep(status="COMPLETED", duration_ms=9200.0)
    violation = evaluator.evaluate(rep)
    assert violation is not None
    assert violation.reason_code == AssessmentReasonCode.DISCARDED_TIMEOUT.value
    assert violation.severity == Severity.REJECT
    assert violation.evidence is not None
    assert violation.evidence.measured_value == 9200.0
    assert "耗时过长" in violation.feedback_text


def test_cycle_rule_nan_duration_protection():
    evaluator = CycleIntegrityEvaluator()
    rep = make_rep(status="COMPLETED", duration_ms=float("nan"))
    violation = evaluator.evaluate(rep)
    assert violation is not None
    assert violation.reason_code == AssessmentReasonCode.FEATURE_DEGENERATE.value
    assert violation.severity == Severity.REJECT
