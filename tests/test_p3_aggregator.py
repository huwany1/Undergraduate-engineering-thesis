# -*- coding: utf-8 -*-
"""
P3 自动化测试套件：结果仲裁、严重度排序与一票否决聚合测试
"""

import pytest
from p3_rules.contracts import (
    AssessmentStatus,
    RuleViolation,
    Severity,
    AssessmentReasonCode,
)
from p3_rules.aggregator.arbitrator import AssessmentAggregator


def test_aggregator_all_passed_acceptable():
    aggregator = AssessmentAggregator()
    status = aggregator.determine_status(gate_passed=True, violations=[])
    assert status == AssessmentStatus.ACCEPTABLE
    primary_code = aggregator.get_primary_reason_code(status, [])
    assert primary_code == AssessmentReasonCode.ACCEPTABLE.value


def test_aggregator_dual_defects_deterministic_order():
    """验证严重度权重优先：WARNING_SEVERE 优先于 WARNING_MILD"""
    aggregator = AssessmentAggregator()

    v_depth = RuleViolation(
        rule_id="R-DEPTH-001",
        reason_code=AssessmentReasonCode.INSUFFICIENT_DEPTH.value,
        severity=Severity.WARNING_MILD,
    )
    v_lean = RuleViolation(
        rule_id="R-LEAN-001",
        reason_code=AssessmentReasonCode.EXCESSIVE_TORSO_LEAN.value,
        severity=Severity.WARNING_SEVERE,
    )

    # 乱序传入 (先传入深度，再传入前倾)
    sorted_v = aggregator.sort_violations([v_depth, v_lean])
    assert len(sorted_v) == 2
    assert sorted_v[0].rule_id == "R-LEAN-001"  # 严重度高者排在第一位
    assert sorted_v[1].rule_id == "R-DEPTH-001"

    status = aggregator.determine_status(gate_passed=True, violations=sorted_v)
    assert status == AssessmentStatus.NEEDS_IMPROVEMENT
    primary_code = aggregator.get_primary_reason_code(status, sorted_v)
    assert primary_code == AssessmentReasonCode.EXCESSIVE_TORSO_LEAN.value


def test_aggregator_equal_severity_lexicographical_order():
    """验证同等严重度下，按 rule_id 字典序严格排列"""
    aggregator = AssessmentAggregator()

    v_lean = RuleViolation(
        rule_id="R-LEAN-001",
        reason_code=AssessmentReasonCode.EXCESSIVE_TORSO_LEAN.value,
        severity=Severity.WARNING_SEVERE,
    )
    v_depth = RuleViolation(
        rule_id="R-DEPTH-001",
        reason_code=AssessmentReasonCode.INSUFFICIENT_DEPTH.value,
        severity=Severity.WARNING_SEVERE,
    )

    # 乱序传入：先 LEAN 后 DEPTH
    sorted_v = aggregator.sort_violations([v_lean, v_depth])
    assert sorted_v[0].rule_id == "R-DEPTH-001"  # D 领先于 L
    assert sorted_v[1].rule_id == "R-LEAN-001"


def test_aggregator_order_invariance_under_input_shuffling():
    """验证输入顺序改变时，输出排序 100% 字节级一致"""
    aggregator = AssessmentAggregator()

    v1 = RuleViolation(rule_id="R-A", reason_code="A", severity=Severity.WARNING_MILD)
    v2 = RuleViolation(rule_id="R-B", reason_code="B", severity=Severity.WARNING_SEVERE)
    v3 = RuleViolation(rule_id="R-C", reason_code="C", severity=Severity.WARNING_MILD)

    res1 = aggregator.sort_violations([v1, v2, v3])
    res2 = aggregator.sort_violations([v3, v2, v1])
    res3 = aggregator.sort_violations([v2, v1, v3])

    order1 = [v.rule_id for v in res1]
    order2 = [v.rule_id for v in res2]
    order3 = [v.rule_id for v in res3]

    assert order1 == ["R-B", "R-A", "R-C"]
    assert order1 == order2 == order3


def test_aggregator_gate_rejection_overrides_quality():
    """验证一票否决制：门控失败覆盖全部质量项"""
    aggregator = AssessmentAggregator()

    v_gate = RuleViolation(
        rule_id="R-CYCLE-001",
        reason_code=AssessmentReasonCode.INCOMPLETE_REP.value,
        severity=Severity.REJECT,
    )
    v_quality = RuleViolation(
        rule_id="R-DEPTH-001",
        reason_code=AssessmentReasonCode.INSUFFICIENT_DEPTH.value,
        severity=Severity.WARNING_MILD,
    )

    status = aggregator.determine_status(gate_passed=False, violations=[v_gate, v_quality])
    assert status == AssessmentStatus.NOT_EVALUATED
    primary = aggregator.get_primary_reason_code(status, [v_gate, v_quality])
    assert primary == AssessmentReasonCode.INCOMPLETE_REP.value
