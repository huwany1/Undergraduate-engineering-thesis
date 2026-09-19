# -*- coding: utf-8 -*-
"""
P2 时序闭环：核心数据合同、状态机枚举与中立 DTO
依据: P2_时序闭环_详细实施方案.md (Section 10)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any


class FsmState(str, Enum):
    STANDING = "STANDING"
    DESCENDING = "DESCENDING"
    BOTTOM = "BOTTOM"
    ASCENDING = "ASCENDING"
    DEGRADED = "DEGRADED"


class RepetitionEvent(str, Enum):
    NONE = "NONE"
    PHASE_ENTER = "PHASE_ENTER"
    REP_COMPLETED = "REP_COMPLETED"
    REP_ABORTED = "REP_ABORTED"
    REP_DISRUPTED = "REP_DISRUPTED"


class TemporalReasonCode(str, Enum):
    NORMAL = "NORMAL"
    ABORTED_INCOMPLETE_DEPTH = "ABORTED_INCOMPLETE_DEPTH"
    DISCARDED_TOO_FAST = "DISCARDED_TOO_FAST"
    DISCARDED_TIMEOUT = "DISCARDED_TIMEOUT"
    SOFT_LOCKOUT_COMPLETED = "SOFT_LOCKOUT_COMPLETED"
    TEMPORAL_GAP_RESET = "TEMPORAL_GAP_RESET"
    OCCLUSION_DEGRADED = "OCCLUSION_DEGRADED"
    FEATURE_DEGENERATE_GEOMETRY = "FEATURE_DEGENERATE_GEOMETRY"


@dataclass
class MotionKinematics:
    """单帧计算出的生理运动学特征（原始与滤波后）"""
    raw_knee_angle: float
    filtered_knee_angle: float
    knee_angular_velocity: float
    raw_torso_angle: float
    filtered_torso_angle: float
    torso_angular_velocity: float
    hip_y_norm: float
    is_valid: bool = True
    knee_valgus_ratio: Optional[float] = None
    heel_lift_deg: Optional[float] = None
    pelvic_tilt_deg: Optional[float] = None
    bilateral_knee_diff: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "raw_knee_angle": round(self.raw_knee_angle, 2),
            "filtered_knee_angle": round(self.filtered_knee_angle, 2),
            "knee_angular_velocity": round(self.knee_angular_velocity, 2),
            "raw_torso_angle": round(self.raw_torso_angle, 2),
            "filtered_torso_angle": round(self.filtered_torso_angle, 2),
            "torso_angular_velocity": round(self.torso_angular_velocity, 2),
            "hip_y_norm": round(self.hip_y_norm, 4),
            "is_valid": self.is_valid,
        }
        if self.knee_valgus_ratio is not None:
            d["knee_valgus_ratio"] = round(self.knee_valgus_ratio, 3)
        if self.heel_lift_deg is not None:
            d["heel_lift_deg"] = round(self.heel_lift_deg, 2)
        if self.pelvic_tilt_deg is not None:
            d["pelvic_tilt_deg"] = round(self.pelvic_tilt_deg, 2)
        if self.bilateral_knee_diff is not None:
            d["bilateral_knee_diff"] = round(self.bilateral_knee_diff, 2)
        return d


@dataclass
class RepetitionRecord:
    """单个动作生命周期切片实体"""
    rep_id: int
    is_valid: bool
    status: str                         # "COMPLETED" | "ABORTED" | "DISRUPTED"
    start_frame: int
    bottom_frame: int
    end_frame: int
    start_timeline_us: int
    bottom_timeline_us: int
    end_timeline_us: int
    duration_ms: float
    descending_duration_ms: float
    ascending_duration_ms: float
    min_knee_angle: float
    max_torso_lean_angle: float
    reason_codes: List[str] = field(default_factory=list)
    extended_metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rep_id": self.rep_id,
            "is_valid": self.is_valid,
            "status": self.status,
            "start_frame": self.start_frame,
            "bottom_frame": self.bottom_frame,
            "end_frame": self.end_frame,
            "start_timeline_us": self.start_timeline_us,
            "bottom_timeline_us": self.bottom_timeline_us,
            "end_timeline_us": self.end_timeline_us,
            "duration_ms": round(self.duration_ms, 1),
            "descending_duration_ms": round(self.descending_duration_ms, 1),
            "ascending_duration_ms": round(self.ascending_duration_ms, 1),
            "min_knee_angle": round(self.min_knee_angle, 2),
            "max_torso_lean_angle": round(self.max_torso_lean_angle, 2),
            "reason_codes": self.reason_codes,
            "extended_metrics": self.extended_metrics,
        }


@dataclass
class P2FrameResult:
    """逐帧时序闭环输出中立 DTO"""
    frame_index: int
    timeline_us: int
    fsm_state: FsmState
    cumulative_rep_count: int
    event: RepetitionEvent
    kinematics: MotionKinematics
    active_rep_id: Optional[int] = None
    reason_codes: List[TemporalReasonCode] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "timeline_us": self.timeline_us,
            "fsm_state": self.fsm_state.value,
            "cumulative_rep_count": self.cumulative_rep_count,
            "event": self.event.value,
            "kinematics": self.kinematics.to_dict(),
            "active_rep_id": self.active_rep_id,
            "reason_codes": [rc.value for rc in self.reason_codes],
        }
