# -*- coding: utf-8 -*-
"""
Web 演示系统通用数据契约与统一模式定义 (Web Demo Contracts & Schema)
五大架构指标保障:
1. 低耦合 (Low Coupling): 提炼统一的 AssessmentReportDto 契约与 UniversalFeedbackFormatter,
   消灭业务层对特定用例 (TC_01~05) 的硬编码判断, 保证黄金用例、开源数据集、用户上传和实时流同构;
2. 可维护性 (Maintainability): 提供 Schema 验证与数据标准化工具, 严格约束前后端数据传输边界.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum


class ReportStatus(str, Enum):
    """评估状态枚举"""
    ACCEPTABLE = "ACCEPTABLE"
    NEEDS_IMPROVEMENT = "NEEDS_IMPROVEMENT"
    REJECTED = "REJECTED"
    NOT_EVALUATED = "NOT_EVALUATED"
    UNKNOWN = "UNKNOWN"


@dataclass
class TelemetryPointDto:
    """逐帧遥测数据传输对象"""
    frame_index: int
    time_s: float
    knee_angle: float
    raw_knee_angle: float
    torso_angle: float
    raw_torso_angle: float
    fsm_state: str
    event: str
    is_valid: bool
    count: int
    landmarks: List[List[float]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class KeyframeDto:
    """关键动作特征帧数据传输对象"""
    event_type: str
    frame_index: int
    timeline_us: int
    description: str
    image_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AssessmentReportDto:
    """
    通用评估报告契约数据传输对象 (Canonical Assessment Report DTO)
    所有测试用例、开源数据集、用户自定义上传视频及实时流会话均必须符合此契约
    """
    case_id: str
    case_name: str
    description: str
    actual_count: int
    actual_status: str
    actual_primary_reason: str
    actual_reason_codes: List[str]
    measured_min_knee_angle: float
    measured_max_torso_angle: float
    execution_time_ms: float
    summary_feedback: str
    has_video: bool
    video_url: Optional[str]
    telemetry: List[Dict[str, Any]] = field(default_factory=list)
    keyframes: List[Dict[str, Any]] = field(default_factory=list)
    repetitions: List[Dict[str, Any]] = field(default_factory=list)
    multi_rep_summary: Optional[Dict[str, Any]] = None
    extended_biomechanics: Optional[Dict[str, Any]] = None
    expected_count: Optional[int] = None
    expected_status: Optional[str] = None
    expected_primary_reason: Optional[str] = None
    camera_view: Optional[str] = None
    assessments: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class UniversalFeedbackFormatter:
    """
    通用动作反馈与指导文案格式化器 (Universal Feedback Formatter)
    职责:
    基于标准原因码、动作状态、实测关节角度与安全阈值, 证据化动态生成非医疗运动建议;
    彻底消除根据特定 case_id 字符串的硬编码逻辑分支.
    """

    KNEE_TARGET_DEG = 105.0
    TORSO_MAX_DEG = 45.0

    @classmethod
    def format(
        cls,
        status: str,
        primary_reason: str,
        min_knee: float,
        max_torso: float,
        total_reps: int = 1,
        all_reasons: Optional[List[str]] = None,
    ) -> str:
        reasons = set(all_reasons or [])
        if primary_reason:
            reasons.add(primary_reason)

        # 1. 前置质检门控一票否决 (画幅越界 / 遮挡)
        if "OUT_OF_FRAME" in reasons or primary_reason == "OUT_OF_FRAME" or status == "REJECTED":
            return (
                "前置质检门控一票否决：检测到受试者移出有效画幅，关键运动特征点缺失。"
                "系统克制地拒绝输出动作次数与质量评价，请调整摄像机机位确保全身入镜。"
            )

        # 2. 规范达标动作 (ACCEPTABLE 且无明显违规)
        if status == "ACCEPTABLE" and (not reasons or reasons.issubset({"NONE", "PERFECT", "", "OK"})):
            return (
                f"动作规范度良好。膝关节最小屈曲角达到 {min_knee:.1f}°（标准阈值 <= {cls.KNEE_TARGET_DEG:.1f}°），"
                f"躯干最大前倾角保持在 {max_torso:.1f}°（安全阈值 <= {cls.TORSO_MAX_DEG:.1f}°），动作平稳且完整。"
            )

        # 3. 复合缺陷 (同时存在下蹲不足与前倾过大)
        has_depth_defect = "INSUFFICIENT_DEPTH" in reasons or "R-DEPTH-001" in reasons
        has_lean_defect = "EXCESSIVE_TORSO_LEAN" in reasons or "R-LEAN-001" in reasons

        # 容错：当原因码为复合标志或两个角度均超标时
        if (has_depth_defect and has_lean_defect) or (min_knee > cls.KNEE_TARGET_DEG and max_torso > cls.TORSO_MAX_DEG):
            return (
                f"动作要点待改进（复合问题）：检测到下蹲深度不足（膝角 {min_knee:.1f}° > {cls.KNEE_TARGET_DEG:.1f}°）"
                f"且躯干前倾过大（前倾角 {max_torso:.1f}° > {cls.TORSO_MAX_DEG:.1f}°）。"
                "建议适当减小动作速度，优先维持躯干直立再逐步增加下蹲深度。"
            )

        # 4. 单项缺陷：下蹲深度不足
        if has_depth_defect or min_knee > cls.KNEE_TARGET_DEG:
            return (
                f"动作要点待改进：下蹲深度不足。实测膝关节最小屈曲角为 {min_knee:.1f}°，"
                f"未触达及格阈值 {cls.KNEE_TARGET_DEG:.1f}°。建议训练时在保持核心收紧的前提下，适度加深髋部下沉幅度。"
            )

        # 5. 单项缺陷：躯干前倾过大
        if has_lean_defect or max_torso > cls.TORSO_MAX_DEG:
            return (
                f"动作要点待改进：躯干前倾幅度偏大。实测躯干最大前倾角为 {max_torso:.1f}°，"
                f"超过基准线 {cls.TORSO_MAX_DEG:.1f}°。建议下蹲时挺胸沉肩，目视前方，保持脊柱中立位。"
            )

        # 6. 未完成闭环 / 动作超时
        if "INCOMPLETE_CYCLE" in reasons or "CYCLE_TIMEOUT" in reasons:
            return (
                f"未检测到完整闭环的深蹲动作（实测最小膝角 {min_knee:.1f}°）。"
                "请在训练时保持核心稳定，下蹲至大腿接近水平再平稳站起恢复直立。"
            )

        # 7. 其他拓展生物力学提示
        bio_notes = []
        if "KNEE_VALGUS_DETECTED" in reasons:
            bio_notes.append("检测到膝关节内扣迹象，建议下蹲时膝盖朝向第二脚趾方向展开")
        if "HEEL_LIFT_DETECTED" in reasons:
            bio_notes.append("检测到脚后跟轻微离地，建议重心均匀分布在全脚掌")
        if "PELVIC_TILT_DETECTED" in reasons:
            bio_notes.append("检测到底部骨盆翻转（屁股眨眼），建议适度收紧核心并调整站距")
        if "BILATERAL_ASYMMETRY_DETECTED" in reasons:
            bio_notes.append("检测到双腿下蹲幅度轻微不对称，建议注意双侧均匀发力")

        if bio_notes:
            return "动作要点待改进：" + "；".join(bio_notes) + "。"

        # 8. 默认兜底文案
        return f"评估状态: {status}, 主原因码: {primary_reason}。"


def validate_report_dict(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    通用评估报告契约 Schema 校验器 (Schema Validator)
    验证字典是否符合生产级 AssessmentReportDto 规范
    返回 (is_valid, error_list)
    """
    errors = []
    required_fields = [
        "case_id",
        "case_name",
        "actual_count",
        "actual_status",
        "actual_primary_reason",
        "measured_min_knee_angle",
        "measured_max_torso_angle",
        "summary_feedback",
        "has_video",
        "telemetry",
        "keyframes",
    ]

    for f_name in required_fields:
        if f_name not in data:
            errors.append(f"Missing required field: '{f_name}'")

    if "telemetry" in data and not isinstance(data["telemetry"], list):
        errors.append("Field 'telemetry' must be a list")

    if "keyframes" in data and not isinstance(data["keyframes"], list):
        errors.append("Field 'keyframes' must be a list")

    if "actual_status" in data and data["actual_status"] not in [
        "ACCEPTABLE",
        "NEEDS_IMPROVEMENT",
        "REJECTED",
        "NOT_EVALUATED",
        "UNKNOWN",
    ]:
        errors.append(f"Invalid actual_status: {data['actual_status']}")

    return (len(errors) == 0, errors)
