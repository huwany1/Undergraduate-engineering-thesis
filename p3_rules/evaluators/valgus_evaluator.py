# -*- coding: utf-8 -*-
"""
R-VALGUS-001 最低点膝关节内扣代理规则评估器
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
    ValgusRuleConfig,
)


class KneeValgusEvaluator(BaseRuleEvaluator):
    """膝关节内扣评估器 (R-VALGUS-001)"""

    def __init__(self, config: Optional[ValgusRuleConfig] = None):
        self.config = config or ValgusRuleConfig()

    def evaluate(self, rep: RepetitionRecord) -> Optional[RuleViolation]:
        # 从扩展指标字典中获取极小内扣比率
        valgus_ratio = rep.extended_metrics.get("min_valgus_ratio") if rep.extended_metrics else None

        # 视点不可观测（纯侧视遮挡或置信度不足）时优雅降级，不误报
        if valgus_ratio is None:
            return None

        # 浮点有效性防御
        if math.isnan(valgus_ratio) or math.isinf(valgus_ratio):
            return RuleViolation(
                rule_id=self.config.rule_id,
                reason_code=AssessmentReasonCode.FEATURE_DEGENERATE.value,
                severity=Severity.REJECT,
                evidence=None,
                feedback_text="膝踝间距比率时序数据异常，本次不作膝内扣评价。",
            )

        delta = self.config.threshold_ratio - valgus_ratio

        # 1. 达标：双膝未向内扣紧（内扣比率大于等于阈值）
        if delta <= 0.0:
            return None

        # 2. 内扣超标，判定严重度级别
        is_mild = delta <= self.config.tolerance_ratio
        severity = Severity.WARNING_MILD if is_mild else Severity.WARNING_SEVERE

        evidence = RuleEvidence(
            feature_name="min_valgus_ratio",
            measured_value=valgus_ratio,
            threshold_value=self.config.threshold_ratio,
            delta_value=delta,
            unit="ratio",
            trigger_frame_index=rep.bottom_frame,
            trigger_timeline_us=rep.bottom_timeline_us,
        )

        if is_mild:
            feedback_text = (
                f"提示：下蹲波谷时双膝略有内扣倾向（测得膝踝间距比 {valgus_ratio:.2f}，参考标准 ≥ {self.config.threshold_ratio:.2f}），"
                "建议下蹲与起立过程中双膝主动对准第二脚趾方向外展。"
            )
        else:
            feedback_text = (
                f"提示：下蹲过程中检测到明显的膝关节内扣（测得膝踝间距比 {valgus_ratio:.2f}，参考标准 ≥ {self.config.threshold_ratio:.2f}），"
                "建议下蹲时强化臀部外展肌群发力，保持双膝稳定朝向脚尖。"
            )

        return RuleViolation(
            rule_id=self.config.rule_id,
            reason_code=AssessmentReasonCode.KNEE_VALGUS.value,
            severity=severity,
            evidence=evidence,
            feedback_text=feedback_text,
        )
