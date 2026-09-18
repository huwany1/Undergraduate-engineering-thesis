# -*- coding: utf-8 -*-
"""
P4 验证包核心数据合同、枚举与 DTO 定义
依据: P4_验证包_详细实施方案.md (Section 10)
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple


class TestCaseId(str, Enum):
    __test__ = False  # 阻止 pytest 将其误识别为测试用例类
    TC_01_PERFECT_SQUAT = "TC_01_PERFECT_SQUAT"
    TC_02_SHALLOW_SQUAT = "TC_02_SHALLOW_SQUAT"
    TC_03_EXCESSIVE_LEAN = "TC_03_EXCESSIVE_LEAN"
    TC_04_DUAL_DEFECT = "TC_04_DUAL_DEFECT"
    TC_05_OUT_OF_FRAME = "TC_05_OUT_OF_FRAME"


class VerificationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"


class KeyframeEventType(str, Enum):
    STANDING_BASELINE = "STANDING_BASELINE"
    BOTTOM_INFLECTION = "BOTTOM_INFLECTION"
    LEAN_PEAK = "LEAN_PEAK"
    COMPLETION_SUMMARY = "COMPLETION_SUMMARY"
    GATE_REJECTED = "GATE_REJECTED"


@dataclass(slots=True)
class ToleranceBand:
    """角度判定安全容差带"""
    knee_min_deg: Tuple[float, float] = (0.0, 100.0)      # 合格膝角区间 [min, max]
    torso_max_deg: Tuple[float, float] = (0.0, 35.0)      # 合格躯干前倾区间 [min, max]
    angle_margin_deg: float = 1.0                         # 跨平台测量浮点舍入容差

    def to_dict(self) -> Dict[str, Any]:
        return {
            "knee_min_deg": list(self.knee_min_deg),
            "torso_max_deg": list(self.torso_max_deg),
            "angle_margin_deg": self.angle_margin_deg,
        }


@dataclass(slots=True)
class GoldenSampleSpec:
    """单个黄金测试样本规范契约"""
    case_id: TestCaseId
    case_name: str
    description: str
    video_path: Optional[str]
    sha256_hash: str
    expected_count: int
    expected_status: str                     # ACCEPTABLE / NEEDS_IMPROVEMENT / NOT_EVALUATED
    expected_primary_reason: str             # 期望主原因码
    expected_reason_codes: List[str]         # 期望触发的全量原因码
    tolerance_band: ToleranceBand = field(default_factory=ToleranceBand)
    camera_view: str = "SAGITTAL_RIGHT"
    is_synthetic: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id.value,
            "case_name": self.case_name,
            "description": self.description,
            "video_path": self.video_path,
            "sha256_hash": self.sha256_hash,
            "expected_count": self.expected_count,
            "expected_status": self.expected_status,
            "expected_primary_reason": self.expected_primary_reason,
            "expected_reason_codes": self.expected_reason_codes,
            "tolerance_band": self.tolerance_band.to_dict(),
            "camera_view": self.camera_view,
            "is_synthetic": self.is_synthetic,
        }


@dataclass(slots=True)
class ScreenshotArtifact:
    """抓取的语义特征截图凭据"""
    event_type: KeyframeEventType
    case_id: TestCaseId
    frame_index: int
    timeline_us: int
    file_path: str
    description: str
    sha256_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "case_id": self.case_id.value,
            "frame_index": self.frame_index,
            "timeline_us": self.timeline_us,
            "file_path": self.file_path,
            "description": self.description,
            "sha256_hash": self.sha256_hash,
        }


@dataclass(slots=True)
class CaseVerificationResult:
    """单个测试用例核验产出结果"""
    case_id: TestCaseId
    status: VerificationStatus
    actual_count: int
    actual_status: str
    actual_primary_reason: str
    actual_reason_codes: List[str]
    measured_min_knee_angle: float
    measured_max_torso_angle: float
    diff_reasons: List[str] = field(default_factory=list)
    execution_time_ms: float = 0.0
    keyframes: List[ScreenshotArtifact] = field(default_factory=list)
    annotated_video_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id.value,
            "status": self.status.value,
            "actual_count": self.actual_count,
            "actual_status": self.actual_status,
            "actual_primary_reason": self.actual_primary_reason,
            "actual_reason_codes": self.actual_reason_codes,
            "measured_min_knee_angle": round(self.measured_min_knee_angle, 2),
            "measured_max_torso_angle": round(self.measured_max_torso_angle, 2),
            "diff_reasons": self.diff_reasons,
            "execution_time_ms": round(self.execution_time_ms, 2),
            "keyframes": [kf.to_dict() for kf in self.keyframes],
            "annotated_video_path": self.annotated_video_path,
        }


@dataclass(slots=True)
class ValidationPackageSummary:
    """全套验证包交付与审计总览"""
    baseline_id: str
    git_commit: str
    timestamp: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    concordance_rate: float
    mae_count: float
    rejection_rate: float
    case_results: List[CaseVerificationResult]
    artifacts_manifest: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "baseline_id": self.baseline_id,
            "git_commit": self.git_commit,
            "timestamp": self.timestamp,
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "concordance_rate": round(self.concordance_rate, 4),
            "mae_count": round(self.mae_count, 4),
            "rejection_rate": round(self.rejection_rate, 4),
            "case_results": [res.to_dict() for res in self.case_results],
            "artifacts_manifest": self.artifacts_manifest,
        }
