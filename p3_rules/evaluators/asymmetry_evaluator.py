# -*- coding: utf-8 -*-
"""
R-ASYM-001 动作双侧不对称代理规则评估器
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
    AsymmetryRuleConfig,
)


class BilateralAsymmetryEvaluator(BaseRuleEvaluator):
    """动作双侧不对称评估器 (R-ASYM-001)"""

    def __init__(self, config: Optional[AsymmetryRuleConfig] = None):
        self.config = config or AsymmetryRuleConfig()

    def evaluate(self, rep: RepetitionRecord) -> Optional[RuleViolation]:
        diff_deg = rep.extended_metrics.get("max_bilateral_diff_deg") if rep.extended_metrics else None

        # 视点不可观测（纯侧视单侧遮挡或置信度不足）时优雅降级，不误报
        if diff_deg is None:
            return None

        # 浮点有效性防御
        if math.isnan(diff_deg) or math.isinf(diff_deg):
            return RuleViolation(
                rule_id=self.config.rule_id,
                reason_code=AssessmentReasonCode.FEATURE_DEGENERATE.value,
                severity=Severity.REJECT,
                evidence=None,
                feedback_text="双侧屈曲角度差异数据异常，本次不作对称性评价。",
            )

        delta = diff_deg - self.config.threshold_deg

        # 1. 达标：左右双腿屈曲动作对称
        if delta <= 0.0:
            return None

        # 2. 不对称超标，判定严重度级别
        is_mild = delta <= self.config.tolerance_deg
        severity = Severity.WARNING_MILD if is_mild else Severity.WARNING_SEVERE

        evidence = RuleEvidence(
            feature_name="max_bilateral_diff_deg",
            measured_value=diff_deg,
            threshold_value=self.config.threshold_deg,
            delta_value=delta,
            unit="deg",
            trigger_frame_index=rep.bottom_frame,
            trigger_timeline_us=rep.bottom_timeline_us,
        )

        if is_mild:
            feedback_text = (
                f"提示：双腿屈曲角度略有不对称（实测两侧相差 {diff_deg:.1f}°，参考标准 ≤ {self.config.threshold_deg:.1f}°），"
                "建议双侧下肢尽量同步发力。"
            )
        else:
            feedback_text = (
                f"提示：检测到显著的动作双侧不对称代偿（实测两侧相差 {diff_deg:.1f}°，参考标准 ≤ {self.config.threshold_deg:.1f}°），"
                "建议双脚对称站位，保持重心居中与双腿均匀发力。"
            )

        return RuleViolation(
            rule_id=self.config.rule_id,
            reason_code=AssessmentReasonCode.BILATERAL_ASYMMETRY.value,
            severity=severity,
            evidence=evidence,
            feedback_text=feedback_text,
        )
