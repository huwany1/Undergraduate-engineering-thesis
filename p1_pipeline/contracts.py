# -*- coding: utf-8 -*-
"""
P1 姿态视频链路：核心数据合同与中立 DTO 定义
依据: P1_姿态视频链路_P0级详细实施方案.md (Section 04 & 05)
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Optional, Dict, Any
import numpy as np


class RunStatus(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BLOCKED_ENGINE_UNRESOLVED = "BLOCKED_ENGINE_UNRESOLVED"


class ProcessingStatus(str, Enum):
    OK = "OK"
    INFERENCE_FAILED = "INFERENCE_FAILED"
    INVALID_MODEL_OUTPUT = "INVALID_MODEL_OUTPUT"


class PoseStatus(str, Enum):
    POSE_DETECTED = "POSE_DETECTED"
    NO_POSE = "NO_POSE"
    INVALID_MODEL_OUTPUT = "INVALID_MODEL_OUTPUT"


class OverlayStatus(str, Enum):
    DRAWABLE = "DRAWABLE"
    POSE_ABSENT = "POSE_ABSENT"
    REQUIRED_JOINT_INVALID = "REQUIRED_JOINT_INVALID"
    SIDE_AMBIGUOUS = "SIDE_AMBIGUOUS"
    SIDE_CHANGED = "SIDE_CHANGED"
    RENDER_SUPPRESSED = "RENDER_SUPPRESSED"


class Side(str, Enum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    UNKNOWN = "UNKNOWN"


class TimeBasis(str, Enum):
    SOURCE_PTS = "source_pts"
    DERIVED_CFR_NONRELEASE = "derived_cfr_nonrelease"


class ReasonCode(str, Enum):
    # 输入组
    INPUT_NOT_FOUND = "INPUT_NOT_FOUND"
    UNSUPPORTED_CONTAINER = "UNSUPPORTED_CONTAINER"
    NO_DECODABLE_FRAMES = "NO_DECODABLE_FRAMES"
    FPS_UNAVAILABLE = "FPS_UNAVAILABLE"
    PTS_NON_MONOTONIC = "PTS_NON_MONOTONIC"
    P0_PERMIT_INVALID = "P0_PERMIT_INVALID"

    # 引擎组
    MODEL_ASSET_MISSING = "MODEL_ASSET_MISSING"
    MODEL_HASH_MISMATCH = "MODEL_HASH_MISMATCH"
    ENGINE_INIT_FAILED = "ENGINE_INIT_FAILED"
    POSE_INFERENCE_FAILED = "POSE_INFERENCE_FAILED"
    INVALID_MODEL_OUTPUT = "INVALID_MODEL_OUTPUT"

    # 帧质量组
    NO_POSE = "NO_POSE"
    REQUIRED_JOINT_NONFINITE = "REQUIRED_JOINT_NONFINITE"
    REQUIRED_JOINT_OUT_OF_FRAME = "REQUIRED_JOINT_OUT_OF_FRAME"
    REQUIRED_JOINT_LOW_VISIBILITY = "REQUIRED_JOINT_LOW_VISIBILITY"
    POSE_SIDE_AMBIGUOUS = "POSE_SIDE_AMBIGUOUS"
    POSE_SIDE_CHANGED = "POSE_SIDE_CHANGED"

    # 输出/运行组
    OUTPUT_CODEC_UNAVAILABLE = "OUTPUT_CODEC_UNAVAILABLE"
    OUTPUT_WRITE_FAILED = "OUTPUT_WRITE_FAILED"
    INTERNAL_ORDER_VIOLATION = "INTERNAL_ORDER_VIOLATION"
    HANG_TIMEOUT = "HANG_TIMEOUT"
    CANCELLED = "CANCELLED"


@dataclass
class LandmarkPoint:
    """单个姿态关键点（支持 3D 归一化/图像坐标，visibility/presence 可为 null，绝不写死为 0）"""
    x: float
    y: float
    z: float = 0.0
    visibility: Optional[float] = None
    presence: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "visibility": self.visibility,
            "presence": self.presence,
        }


@dataclass
class PoseFrameResult:
    """引擎中立端口输出（阻断引擎 SDK 对象）"""
    processing_status: ProcessingStatus
    pose_status: PoseStatus
    landmarks_2d: List[LandmarkPoint] = field(default_factory=list)
    landmarks_world: Optional[List[LandmarkPoint]] = None
    engine_diagnostic: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "processing_status": self.processing_status.value,
            "pose_status": self.pose_status.value,
            "landmarks_2d": [p.to_dict() for p in self.landmarks_2d],
            "landmarks_world": [p.to_dict() for p in self.landmarks_world] if self.landmarks_world else None,
            "engine_diagnostic": self.engine_diagnostic,
        }


@dataclass
class FrameEnvelope:
    """解码适配器输出帧信封（携带绝对顺序键与时间线）"""
    run_id: str
    frame_index: int
    timeline_us: int
    decoded_bgr: np.ndarray
    decoded_rgb: np.ndarray
    width: int
    height: int
    rotation_applied: int = 0
    decode_status: str = "OK"
    source_pts: Optional[int] = None
    time_base: Optional[str] = None


@dataclass
class FrameQuality:
    """P1 质量与侧别门控判定结果"""
    overlay_status: OverlayStatus
    required_side: Optional[Side]
    required_joints: List[str]
    joint_validity: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    reason_codes: List[ReasonCode] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overlay_status": self.overlay_status.value,
            "required_side": self.required_side.value if self.required_side else None,
            "required_joints": self.required_joints,
            "joint_validity": self.joint_validity,
            "reason_codes": [rc.value for rc in self.reason_codes],
        }


@dataclass
class RunContext:
    """单次运行上下文契约"""
    run_id: str
    input_path: str
    input_sha256: str
    baseline_id: str
    processing_permit_id: str
    config_hash: str
    overlay_policy_version: str
    engine_id: str
    package_version: str
    time_basis: TimeBasis
    model_sha256: Optional[str] = None


@dataclass
class InputManifest:
    """输入探测报告"""
    video_path: str
    video_sha256: str
    width: int
    height: int
    fps: float
    frame_count_est: int
    permit_id: str
    time_basis: TimeBasis
    camera_profile_id: Optional[str] = None


@dataclass
class ValidationReport:
    """完结校验报告"""
    is_valid: bool
    decoded_count: int
    inferred_count: int
    rendered_count: int
    written_count: int
    sidecar_count: int
    verified_video_frames: int
    checks: Dict[str, bool] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "counts": {
                "decoded_count": self.decoded_count,
                "inferred_count": self.inferred_count,
                "rendered_count": self.rendered_count,
                "written_count": self.written_count,
                "sidecar_count": self.sidecar_count,
                "verified_video_frames": self.verified_video_frames,
            },
            "five_counts_equal": (
                self.decoded_count == self.inferred_count == self.rendered_count ==
                self.written_count == self.sidecar_count == self.verified_video_frames
            ),
            "checks": self.checks,
            "errors": self.errors,
        }
