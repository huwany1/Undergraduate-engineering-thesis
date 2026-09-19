# -*- coding: utf-8 -*-
"""
R-PELVIC-001 深蹲底部骨盆翻转(臀部眨眼)代理规则评估器
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
    PelvicTiltRuleConfig,
)


class PelvicTiltEvaluator(BaseRuleEvaluator):
    """骨盆翻转(臀部眨眼)评估器 (R-PELVIC-001)"""

    def __init__(self, config: Optional[PelvicTiltRuleConfig] = None):
        self.config = config or PelvicTiltRuleConfig()

    def evaluate(self, rep: RepetitionRecord) -> Optional[RuleViolation]:
        pelvic_tilt_deg = rep.extended_metrics.get("max_pelvic_tilt_deg", 0.0) if rep.extended_metrics else 0.0

        if pelvic_tilt_deg is None:
            return None

        # 浮点有效性防御
        if math.isnan(pelvic_tilt_deg) or math.isinf(pelvic_tilt_deg):
            return RuleViolation(
                rule_id=self.config.rule_id,
                reason_code=AssessmentReasonCode.FEATURE_DEGENERATE.value,
                severity=Severity.REJECT,
                evidence=None,
                feedback_text="骨盆翻转时序数据异常，本次不作骨盆态势评价。",
            )

        delta = pelvic_tilt_deg - self.config.threshold_deg

        # 1. 达标：骨盆姿态平稳，未出现明显后倾卷折
        if delta <= 0.0:
            return None

        # 2. 骨盆后倾超标，判定严重度级别
        is_mild = delta <= self.config.tolerance_deg
        severity = Severity.WARNING_MILD if is_mild else Severity.WARNING_SEVERE

        evidence = RuleEvidence(
            feature_name="max_pelvic_tilt_deg",
            measured_value=pelvic_tilt_deg,
            threshold_value=self.config.threshold_deg,
            delta_value=delta,
            unit="deg",
            trigger_frame_index=rep.bottom_frame,
            trigger_timeline_us=rep.bottom_timeline_us,
        )

        if is_mild:
            feedback_text = (
                f"提示：下蹲底部轻微伴有骨盆后倾翻转（测得折角偏差 {pelvic_tilt_deg:.1f}°，参考标准 ≤ {self.config.threshold_deg:.1f}°），"
                "建议底部收紧核心，保持腰椎自然生理曲度。"
            )
        else:
            feedback_text = (
                f"提示：下蹲底部检测到明显的骨盆后倾翻转（臀部眨眼，测得折角偏差 {pelvic_tilt_deg:.1f}°，参考标准 ≤ {self.config.threshold_deg:.1f}°），"
                "建议保持下背部挺直紧绷，可适度控制下蹲深度避免骨盆过度翻转。"
            )

        return RuleViolation(
            rule_id=self.config.rule_id,
            reason_code=AssessmentReasonCode.PELVIC_TILT.value,
            severity=severity,
            evidence=evidence,
            feedback_text=feedback_text,
        )
