# -*- coding: utf-8 -*-
"""
R-CYCLE-001 周期完整性准入规则评估器
依据: P3_规则与反馈_详细实施方案.md (Section 6.1)
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
    CycleRuleConfig,
)


class CycleIntegrityEvaluator(BaseRuleEvaluator):
    """深蹲完整周期与时序有效性准入规则评估器 (R-CYCLE-001)"""

    def __init__(self, config: Optional[CycleRuleConfig] = None):
        self.config = config or CycleRuleConfig()

    def evaluate(self, rep: RepetitionRecord) -> Optional[RuleViolation]:
        # 1. 检查生命周期状态机是否完整闭环
        if rep.status != "COMPLETED" or not rep.is_valid:
            return RuleViolation(
                rule_id=self.config.rule_id,
                reason_code=AssessmentReasonCode.INCOMPLETE_REP.value,
                severity=Severity.REJECT,
                evidence=RuleEvidence(
                    feature_name="status",
                    measured_value=0.0,
                    threshold_value=1.0,
                    delta_value=-1.0,
                    unit="lifecycle_flag",
                    trigger_frame_index=rep.end_frame,
                    trigger_timeline_us=rep.end_timeline_us,
                ),
                feedback_text="动作未完成，未经历完整起蹲周期，不计入有效深蹲。",
            )

        # 2. 检查时长合法性与浮点有效性
        duration = rep.duration_ms
        if math.isnan(duration) or math.isinf(duration):
            return RuleViolation(
                rule_id=self.config.rule_id,
                reason_code=AssessmentReasonCode.FEATURE_DEGENERATE.value,
                severity=Severity.REJECT,
                evidence=None,
                feedback_text="时序特征数据异常，本次不作动作质量评估。",
            )

        if duration < self.config.min_duration_ms:
            return RuleViolation(
                rule_id=self.config.rule_id,
                reason_code=AssessmentReasonCode.DISCARDED_TOO_FAST.value,
                severity=Severity.REJECT,
                evidence=RuleEvidence(
                    feature_name="duration_ms",
                    measured_value=duration,
                    threshold_value=self.config.min_duration_ms,
                    delta_value=duration - self.config.min_duration_ms,
                    unit="ms",
                    trigger_frame_index=rep.end_frame,
                    trigger_timeline_us=rep.end_timeline_us,
                ),
                feedback_text=f"动作完成过快（历时 {round(duration)}ms，建议 ≥ {round(self.config.min_duration_ms)}ms），请放慢动作节奏以获得训练效果。",
            )

        if duration > self.config.max_duration_ms:
            return RuleViolation(
                rule_id=self.config.rule_id,
                reason_code=AssessmentReasonCode.DISCARDED_TIMEOUT.value,
                severity=Severity.REJECT,
                evidence=RuleEvidence(
                    feature_name="duration_ms",
                    measured_value=duration,
                    threshold_value=self.config.max_duration_ms,
                    delta_value=duration - self.config.max_duration_ms,
                    unit="ms",
                    trigger_frame_index=rep.end_frame,
                    trigger_timeline_us=rep.end_timeline_us,
                ),
                feedback_text=f"动作耗时过长（历时 {round(duration)}ms），本次不作动作质量评估。",
            )

        # 准入通过，无违规
        return None
