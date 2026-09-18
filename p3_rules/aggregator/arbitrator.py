# -*- coding: utf-8 -*-
"""
P3 结果仲裁聚合器 (Assessment Aggregator)
依据: P3_规则与反馈_详细实施方案.md (Section 08)
"""

from typing import List, Tuple
from ..contracts import (
    AssessmentStatus,
    RuleViolation,
    Severity,
    AssessmentReasonCode,
)


class AssessmentAggregator:
    """确定性双层全序排序与状态聚合引擎"""

    def __init__(self, policy_version: str = "AGGR-SQUAT-v1.0"):
        self.policy_version = policy_version

    @staticmethod
    def sort_violations(violations: List[RuleViolation]) -> List[RuleViolation]:
        """
        数学定义的全序排序算子:
        SortKey(v) = (-Weight(v.severity), v.rule_id)
        保证：严重度权重降序优先，相同严重度下按 rule_id 字典序严格排列。
        """
        def _sort_key(v: RuleViolation) -> Tuple[int, str]:
            return (-v.severity.weight, v.rule_id)

        return sorted(violations, key=_sort_key)

    @staticmethod
    def determine_status(
        gate_passed: bool,
        violations: List[RuleViolation]
    ) -> AssessmentStatus:
        """
        根据门控通过状态与质量违规列表，推断最终动作评级。
        一票否决制：门控失败或含 REJECT 级别违规，直接归为 NOT_EVALUATED。
        """
        if not gate_passed or any(v.severity == Severity.REJECT for v in violations):
            return AssessmentStatus.NOT_EVALUATED

        if not violations:
            return AssessmentStatus.ACCEPTABLE

        return AssessmentStatus.NEEDS_IMPROVEMENT

    @staticmethod
    def get_primary_reason_code(
        status: AssessmentStatus,
        sorted_violations: List[RuleViolation]
    ) -> str:
        """获取顶层主原因码"""
        if status == AssessmentStatus.ACCEPTABLE:
            return AssessmentReasonCode.ACCEPTABLE.value

        if sorted_violations:
            return sorted_violations[0].reason_code

        if status == AssessmentStatus.NOT_EVALUATED:
            return AssessmentReasonCode.NOT_EVALUATED.value

        return AssessmentReasonCode.RULE_NOT_TRIGGERED.value
