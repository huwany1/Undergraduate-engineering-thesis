# -*- coding: utf-8 -*-
"""
P3 规则与反馈：核心数据合同、枚举与 DTO 定义
依据: P3_规则与反馈_详细实施方案.md (Section 10)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any


class AssessmentStatus(str, Enum):
    """深蹲单次动作总体评级"""
    ACCEPTABLE = "ACCEPTABLE"                  # 动作完整规范，深度与体态达标
    NEEDS_IMPROVEMENT = "NEEDS_IMPROVEMENT"    # 动作完整但存在 1 个或多个质量瑕疵
    NOT_EVALUATED = "NOT_EVALUATED"            # 前置门控未过或数据异常，一票否决不予评价


class Severity(str, Enum):
    """违规严重度分级（用于稳定全序排序）"""
    INFO = "INFO"
    WARNING_MILD = "WARNING_MILD"
    WARNING_SEVERE = "WARNING_SEVERE"
    REJECT = "REJECT"

    @property
    def weight(self) -> int:
        mapping = {
            Severity.INFO: 0,
            Severity.WARNING_MILD: 20,
            Severity.WARNING_SEVERE: 30,
            Severity.REJECT: 100,
        }
        return mapping.get(self, 10)


class AssessmentReasonCode(str, Enum):
    """P3 动作评估原因码全量枚举"""
    # 准入与达标码
    COMPLETE_REP = "COMPLETE_REP"
    RULE_NOT_TRIGGERED = "RULE_NOT_TRIGGERED"
    ACCEPTABLE = "ACCEPTABLE"

    # 质量要点缺陷码
    INSUFFICIENT_DEPTH = "INSUFFICIENT_DEPTH"
    EXCESSIVE_TORSO_LEAN = "EXCESSIVE_TORSO_LEAN"

    # 门控拒绝与异常码
    INCOMPLETE_REP = "INCOMPLETE_REP"
    DISCARDED_TOO_FAST = "DISCARDED_TOO_FAST"
    DISCARDED_TIMEOUT = "DISCARDED_TIMEOUT"
    LOW_VISIBILITY = "LOW_VISIBILITY"
    OUT_OF_FRAME = "OUT_OF_FRAME"
    NO_PERSON = "NO_PERSON"
    FEATURE_DEGENERATE = "FEATURE_DEGENERATE"
    NOT_EVALUATED = "NOT_EVALUATED"


@dataclass(slots=True)
class RuleEvidence:
    """单一规则命中时所附带的物理量与时序证据"""
    feature_name: str
    measured_value: float
    threshold_value: float
    delta_value: float
    unit: str
    trigger_frame_index: int
    trigger_timeline_us: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_name": self.feature_name,
            "measured_value": round(self.measured_value, 2),
            "threshold_value": round(self.threshold_value, 2),
            "delta_value": round(self.delta_value, 2),
            "unit": self.unit,
            "trigger_frame_index": self.trigger_frame_index,
            "trigger_timeline_us": self.trigger_timeline_us,
        }


@dataclass(slots=True)
class RuleViolation:
    """单条规则违规判定实体"""
    rule_id: str
    reason_code: str
    severity: Severity
    evidence: Optional[RuleEvidence] = None
    feedback_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "reason_code": self.reason_code,
            "severity": self.severity.value,
            "evidence": self.evidence.to_dict() if self.evidence else None,
            "feedback_text": self.feedback_text,
        }


@dataclass(slots=True)
class RepetitionAssessment:
    """单次动作顶层结构化评估实体"""
    rep_id: int
    overall_status: AssessmentStatus
    primary_reason_code: str
    violations: List[RuleViolation] = field(default_factory=list)
    summary_feedback: str = ""
    aggregation_policy_version: str = "AGGR-SQUAT-v1.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rep_id": self.rep_id,
            "overall_status": self.overall_status.value,
            "primary_reason_code": self.primary_reason_code,
            "violations": [v.to_dict() for v in self.violations],
            "summary_feedback": self.summary_feedback,
            "aggregation_policy_version": self.aggregation_policy_version,
        }


@dataclass(slots=True)
class CycleRuleConfig:
    """R-CYCLE-001 周期完整性配置"""
    rule_id: str = "R-CYCLE-001"
    min_duration_ms: float = 800.0
    max_duration_ms: float = 8000.0
    min_phase_duration_ms: float = 300.0


@dataclass(slots=True)
class DepthRuleConfig:
    """R-DEPTH-001 下蹲深度代理配置"""
    rule_id: str = "R-DEPTH-001"
    threshold_deg: float = 100.0
    tolerance_deg: float = 3.0


@dataclass(slots=True)
class LeanRuleConfig:
    """R-LEAN-001 躯干前倾代理配置"""
    rule_id: str = "R-LEAN-001"
    threshold_deg: float = 45.0
    tolerance_deg: float = 3.0


@dataclass(slots=True)
class RuleCardConfig:
    """规则卡通用配置载体"""
    cycle_rule: CycleRuleConfig = field(default_factory=CycleRuleConfig)
    depth_rule: DepthRuleConfig = field(default_factory=DepthRuleConfig)
    lean_rule: LeanRuleConfig = field(default_factory=LeanRuleConfig)
    aggregation_policy_version: str = "AGGR-SQUAT-v1.0"


# 别名兼容
RuleSetConfiguration = RuleCardConfig
