# -*- coding: utf-8 -*-
"""
R-LEAN-001 动作全周期最大躯干前倾代理规则评估器
依据: P3_规则与反馈_详细实施方案.md (Section 6.3)
"""

import math
from typing import Optional
from p2_temporal.contracts import RepetitionRecord
from .base import BaseRuleEvaluator
from ..contracts import (
    RuleViolation,
    RuleEvidence,
    Severity,
    AssessmentReasonCode,
    LeanRuleConfig,
)


class TorsoLeanEvaluator(BaseRuleEvaluator):
    """躯干前倾姿态代理规则评估器 (R-LEAN-001)"""

    def __init__(self, config: Optional[LeanRuleConfig] = None):
        self.config = config or LeanRuleConfig()

    def evaluate(self, rep: RepetitionRecord) -> Optional[RuleViolation]:
        lean_angle = rep.max_torso_lean_angle

        # 浮点有效性防御
        if math.isnan(lean_angle) or math.isinf(lean_angle):
            return RuleViolation(
                rule_id=self.config.rule_id,
                reason_code=AssessmentReasonCode.FEATURE_DEGENERATE.value,
                severity=Severity.REJECT,
                evidence=None,
                feedback_text="躯干前倾角时序数据异常，本次不作体态评价。",
            )

        delta = lean_angle - self.config.threshold_deg

        # 1. 躯干倾角在允许范围内 (未超标)
        if delta <= 0.0:
            return None

        # 2. 躯干倾角超标，判定严重度级别
        is_mild = delta <= self.config.tolerance_deg
        severity = Severity.WARNING_MILD if is_mild else Severity.WARNING_SEVERE

        evidence = RuleEvidence(
            feature_name="max_torso_lean_angle",
            measured_value=lean_angle,
            threshold_value=self.config.threshold_deg,
            delta_value=delta,
            unit="deg",
            trigger_frame_index=rep.bottom_frame,
            trigger_timeline_us=rep.bottom_timeline_us,
        )

        if is_mild:
            feedback_text = (
                f"提示：躯干略有前倾（测得前倾角 {lean_angle:.1f}°，参考标准 ≤ {self.config.threshold_deg:.1f}°），"
                "建议下蹲时收紧核心，挺起胸部。"
            )
        else:
            feedback_text = (
                f"提示：躯干过度前倾（测得前倾角 {lean_angle:.1f}°，参考标准 ≤ {self.config.threshold_deg:.1f}°），"
                "建议保持抬头挺胸，目视前方，避免上身过多下压。"
            )

        return RuleViolation(
            rule_id=self.config.rule_id,
            reason_code=AssessmentReasonCode.EXCESSIVE_TORSO_LEAN.value,
            severity=severity,
            evidence=evidence,
            feedback_text=feedback_text,
        )
