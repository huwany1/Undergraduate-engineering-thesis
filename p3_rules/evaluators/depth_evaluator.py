# -*- coding: utf-8 -*-
"""
R-DEPTH-001 最低点膝关节屈曲角深度代理规则评估器
依据: P3_规则与反馈_详细实施方案.md (Section 6.2)
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
    DepthRuleConfig,
)


class SquatDepthEvaluator(BaseRuleEvaluator):
    """深蹲下蹲深度代理规则评估器 (R-DEPTH-001)"""

    def __init__(self, config: Optional[DepthRuleConfig] = None):
        self.config = config or DepthRuleConfig()

    def evaluate(self, rep: RepetitionRecord) -> Optional[RuleViolation]:
        knee_angle = rep.min_knee_angle

        # 浮点有效性防御
        if math.isnan(knee_angle) or math.isinf(knee_angle):
            return RuleViolation(
                rule_id=self.config.rule_id,
                reason_code=AssessmentReasonCode.FEATURE_DEGENERATE.value,
                severity=Severity.REJECT,
                evidence=None,
                feedback_text="膝关节运动学角度数据异常，本次不作深度评价。",
            )

        delta = knee_angle - self.config.threshold_deg

        # 1. 深度达标 (内角小于等于阈值)
        if delta <= 0.0:
            return None

        # 2. 深度未达标，判定严重度级别
        is_mild = delta <= self.config.tolerance_deg
        severity = Severity.WARNING_MILD if is_mild else Severity.WARNING_SEVERE

        evidence = RuleEvidence(
            feature_name="min_knee_angle",
            measured_value=knee_angle,
            threshold_value=self.config.threshold_deg,
            delta_value=delta,
            unit="deg",
            trigger_frame_index=rep.bottom_frame,
            trigger_timeline_us=rep.bottom_timeline_us,
        )

        if is_mild:
            feedback_text = (
                f"提示：下蹲深度稍浅（测得膝角 {knee_angle:.1f}°，参考标准 ≤ {self.config.threshold_deg:.1f}°），"
                "建议下蹲时大腿进一步下沉。"
            )
        else:
            feedback_text = (
                f"提示：下蹲深度显著不足（测得膝角 {knee_angle:.1f}°，参考标准 ≤ {self.config.threshold_deg:.1f}°），"
                "建议髋关节继续下沉至大腿约平行地面。"
            )

        return RuleViolation(
            rule_id=self.config.rule_id,
            reason_code=AssessmentReasonCode.INSUFFICIENT_DEPTH.value,
            severity=severity,
            evidence=evidence,
            feedback_text=feedback_text,
        )
