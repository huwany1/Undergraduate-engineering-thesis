# -*- coding: utf-8 -*-
"""
R-HEEL-001 动作全周期脚后跟离地代理规则评估器
依据: P3_规则与反馈规范 & 维度二实施方案
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
    HeelLiftRuleConfig,
)


class HeelLiftEvaluator(BaseRuleEvaluator):
    """脚后跟离地评估器 (R-HEEL-001)"""

    def __init__(self, config: Optional[HeelLiftRuleConfig] = None):
        self.config = config or HeelLiftRuleConfig()

    def evaluate(self, rep: RepetitionRecord) -> Optional[RuleViolation]:
        heel_lift_deg = rep.extended_metrics.get("max_heel_lift_deg", 0.0) if rep.extended_metrics else 0.0

        if heel_lift_deg is None:
            return None

        # 浮点有效性防御
        if math.isnan(heel_lift_deg) or math.isinf(heel_lift_deg):
            return RuleViolation(
                rule_id=self.config.rule_id,
                reason_code=AssessmentReasonCode.FEATURE_DEGENERATE.value,
                severity=Severity.REJECT,
                evidence=None,
                feedback_text="脚后跟俯仰角数据异常，本次不作脚跟离地评价。",
            )

        delta = heel_lift_deg - self.config.threshold_deg

        # 1. 达标：脚跟未出现明显离地
        if delta <= 0.0:
            return None

        # 2. 离地超标，判定严重度级别
        is_mild = delta <= self.config.tolerance_deg
        severity = Severity.WARNING_MILD if is_mild else Severity.WARNING_SEVERE

        evidence = RuleEvidence(
            feature_name="max_heel_lift_deg",
            measured_value=heel_lift_deg,
            threshold_value=self.config.threshold_deg,
            delta_value=delta,
            unit="deg",
            trigger_frame_index=rep.bottom_frame,
            trigger_timeline_us=rep.bottom_timeline_us,
        )

        if is_mild:
            feedback_text = (
                f"提示：下蹲波谷时脚跟略有抬起（测得抬升角 {heel_lift_deg:.1f}°，参考标准 ≤ {self.config.threshold_deg:.1f}°），"
                "建议重心微向后移，全脚掌踏实地面。"
            )
        else:
            feedback_text = (
                f"提示：下蹲最低点检测到明显的脚后跟离地（测得抬升角 {heel_lift_deg:.1f}°，参考标准 ≤ {self.config.threshold_deg:.1f}°），"
                "建议重心均匀分布于全脚掌，避免身体过度前倾冲膝。"
            )

        return RuleViolation(
            rule_id=self.config.rule_id,
            reason_code=AssessmentReasonCode.HEEL_LIFT.value,
            severity=severity,
            evidence=evidence,
            feedback_text=feedback_text,
        )
