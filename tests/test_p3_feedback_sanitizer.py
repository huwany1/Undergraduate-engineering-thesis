# -*- coding: utf-8 -*-
"""
P3 自动化测试套件：文案格式化与非医疗化敏感词熔断测试
"""

import pytest
from p3_rules.contracts import (
    AssessmentStatus,
    RuleViolation,
    Severity,
    AssessmentReasonCode,
)
from p3_rules.feedback.formatter import FeedbackFormatter
from p3_rules.feedback.sanitizer import (
    SanitizerGate,
    MedicalTerminologyViolationError,
    DISALLOWED_MEDICAL_TERMS,
)


def test_feedback_formatter_acceptable():
    formatter = FeedbackFormatter()
    text = formatter.compose_summary(AssessmentStatus.ACCEPTABLE, [])
    assert text == FeedbackFormatter.TPL_ACCEPTABLE
    assert formatter.sanitizer.is_safe(text)


def test_feedback_formatter_not_evaluated():
    formatter = FeedbackFormatter()
    v_gate = RuleViolation(
        rule_id="R-CYCLE-001",
        reason_code=AssessmentReasonCode.INCOMPLETE_REP.value,
        severity=Severity.REJECT,
        feedback_text="动作未完成，未经历完整起蹲周期，不计入有效深蹲。",
    )
    text = formatter.compose_summary(AssessmentStatus.NOT_EVALUATED, [v_gate])
    assert text == "动作未完成，未经历完整起蹲周期，不计入有效深蹲。"


def test_feedback_formatter_violations_combined():
    formatter = FeedbackFormatter()
    v1 = RuleViolation(
        rule_id="R-DEPTH-001",
        reason_code=AssessmentReasonCode.INSUFFICIENT_DEPTH.value,
        severity=Severity.WARNING_SEVERE,
        feedback_text="提示：下蹲深度显著不足，建议髋关节继续下沉。",
    )
    v2 = RuleViolation(
        rule_id="R-LEAN-001",
        reason_code=AssessmentReasonCode.EXCESSIVE_TORSO_LEAN.value,
        severity=Severity.WARNING_MILD,
        feedback_text="提示：躯干略有前倾，建议收紧核心挺胸。",
    )
    text = formatter.compose_summary(AssessmentStatus.NEEDS_IMPROVEMENT, [v1, v2])
    assert "提示：下蹲深度显著不足" in text
    assert "提示：躯干略有前倾" in text
    assert formatter.sanitizer.is_safe(text)


def test_sanitizer_passes_clean_text():
    gate = SanitizerGate()
    clean_texts = [
        "动作规范，下蹲深度充分，躯干姿态稳定。",
        "建议下蹲时髋关节继续下沉，保持挺胸收腹，动作平稳。",
        "完成 1 次有效深蹲，节奏良好。",
    ]
    for ct in clean_texts:
        assert gate.is_safe(ct)
        gate.validate(ct)  # 不抛出异常


@pytest.mark.parametrize("bad_term", DISALLOWED_MEDICAL_TERMS)
def test_sanitizer_blocks_all_disallowed_medical_terms(bad_term: str):
    gate = SanitizerGate()
    dirty_text = f"本次动作存在风险，可能导致{bad_term}，请注意。"
    assert not gate.is_safe(dirty_text)
    with pytest.raises(MedicalTerminologyViolationError) as exc_info:
        gate.validate(dirty_text)
    assert bad_term in str(exc_info.value)
