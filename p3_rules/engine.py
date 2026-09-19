# -*- coding: utf-8 -*-
"""
P3 深蹲动作评估核心门面引擎 (Squat Assessment Engine)
依据: P3_规则与反馈_详细实施方案.md (Section 10.2)
"""

from typing import List, Optional
from p2_temporal.contracts import RepetitionRecord
from .contracts import (
    RuleCardConfig,
    RepetitionAssessment,
    AssessmentStatus,
    RuleViolation,
)
from .evaluators.cycle_evaluator import CycleIntegrityEvaluator
from .evaluators.depth_evaluator import SquatDepthEvaluator
from .evaluators.lean_evaluator import TorsoLeanEvaluator
from .evaluators.valgus_evaluator import KneeValgusEvaluator
from .evaluators.heel_evaluator import HeelLiftEvaluator
from .evaluators.pelvic_evaluator import PelvicTiltEvaluator
from .evaluators.asymmetry_evaluator import BilateralAsymmetryEvaluator
from .aggregator.arbitrator import AssessmentAggregator
from .feedback.formatter import FeedbackFormatter


class SquatAssessmentEngine:
    """深蹲动作质量辅助评估引擎总门面"""

    def __init__(self, config: Optional[RuleCardConfig] = None):
        self.config = config or RuleCardConfig()
        self.cycle_evaluator = CycleIntegrityEvaluator(self.config.cycle_rule)
        self.depth_evaluator = SquatDepthEvaluator(self.config.depth_rule)
        self.lean_evaluator = TorsoLeanEvaluator(self.config.lean_rule)
        self.valgus_evaluator = KneeValgusEvaluator(self.config.valgus_rule)
        self.heel_evaluator = HeelLiftEvaluator(self.config.heel_rule)
        self.pelvic_evaluator = PelvicTiltEvaluator(self.config.pelvic_rule)
        self.asymmetry_evaluator = BilateralAsymmetryEvaluator(self.config.asymmetry_rule)
        self.aggregator = AssessmentAggregator(self.config.aggregation_policy_version)
        self.formatter = FeedbackFormatter()

    def evaluate_repetition(self, rep: RepetitionRecord) -> RepetitionAssessment:
        """
        对单个动作切片执行完整的四阶段评估流水线：
        1. 门控准入核验 (R-CYCLE-001)
        2. 质量要点匹配 (R-DEPTH-001, R-LEAN-001, R-VALGUS-001, R-HEEL-001, R-PELVIC-001, R-ASYM-001)
        3. 双层全序仲裁聚合 (Severity 权重降序 + rule_id 字典序升序)
        4. 非医疗化证据提示生成与安全门禁校验
        """
        # 1. 准入门禁核验 (一票否决制)
        cycle_violation = self.cycle_evaluator.evaluate(rep)
        if cycle_violation is not None:
            # 门控失败：立即熔断质量评估，短路返回 NOT_EVALUATED
            violations = [cycle_violation]
            overall_status = AssessmentStatus.NOT_EVALUATED
            primary_reason = cycle_violation.reason_code
            summary_text = self.formatter.compose_summary(overall_status, violations)

            return RepetitionAssessment(
                rep_id=rep.rep_id,
                overall_status=overall_status,
                primary_reason_code=primary_reason,
                violations=violations,
                summary_feedback=summary_text,
                aggregation_policy_version=self.config.aggregation_policy_version,
            )

        # 2. 质量要点规则并发执行
        violations: List[RuleViolation] = []

        depth_violation = self.depth_evaluator.evaluate(rep)
        if depth_violation is not None:
            violations.append(depth_violation)

        lean_violation = self.lean_evaluator.evaluate(rep)
        if lean_violation is not None:
            violations.append(lean_violation)

        valgus_violation = self.valgus_evaluator.evaluate(rep)
        if valgus_violation is not None:
            violations.append(valgus_violation)

        heel_violation = self.heel_evaluator.evaluate(rep)
        if heel_violation is not None:
            violations.append(heel_violation)

        pelvic_violation = self.pelvic_evaluator.evaluate(rep)
        if pelvic_violation is not None:
            violations.append(pelvic_violation)

        asymmetry_violation = self.asymmetry_evaluator.evaluate(rep)
        if asymmetry_violation is not None:
            violations.append(asymmetry_violation)

        # 3. 确定性全序排序与状态聚合
        sorted_violations = self.aggregator.sort_violations(violations)
        overall_status = self.aggregator.determine_status(
            gate_passed=True,
            violations=sorted_violations
        )
        primary_reason = self.aggregator.get_primary_reason_code(
            overall_status,
            sorted_violations
        )

        # 4. 生成证据化综合文案
        summary_text = self.formatter.compose_summary(overall_status, sorted_violations)

        return RepetitionAssessment(
            rep_id=rep.rep_id,
            overall_status=overall_status,
            primary_reason_code=primary_reason,
            violations=sorted_violations,
            summary_feedback=summary_text,
            aggregation_policy_version=self.config.aggregation_policy_version,
        )

    def evaluate_all(self, reps: List[RepetitionRecord]) -> List[RepetitionAssessment]:
        """批量评估动作切片列表"""
        return [self.evaluate_repetition(rep) for rep in reps]
