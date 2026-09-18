# -*- coding: utf-8 -*-
"""
P3 规则与反馈引擎 (Rules and Feedback Engine)
提供动作质量评估、三类核心规则判定、确定性全序聚合与非医疗化模板反馈。
"""

from .contracts import (
    AssessmentStatus,
    Severity,
    AssessmentReasonCode,
    RuleEvidence,
    RuleViolation,
    RepetitionAssessment,
    RuleCardConfig,
    RuleSetConfiguration,
)
from .engine import SquatAssessmentEngine

__all__ = [
    "AssessmentStatus",
    "Severity",
    "AssessmentReasonCode",
    "RuleEvidence",
    "RuleViolation",
    "RepetitionAssessment",
    "RuleCardConfig",
    "RuleSetConfiguration",
    "SquatAssessmentEngine",
]
