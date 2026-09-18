# -*- coding: utf-8 -*-
"""
P4 黄金测试样本库与数学合成时序基线生成器
依据: P4_验证包_详细实施方案.md (Section 06)
"""

import math
import hashlib
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

from p1_pipeline.contracts import LandmarkPoint
from .contracts import (
    TestCaseId,
    GoldenSampleSpec,
    ToleranceBand,
)


class SyntheticStreamGenerator:
    """高保真二维时序运动学生成器 (S4 级公开契约基线)"""

    @staticmethod
    def _create_frame_landmarks(
        knee_angle_deg: float,
        torso_angle_deg: float,
        side: str = "LEFT",
        visibility: float = 0.99,
        shift_out_of_frame: bool = False,
    ) -> List[LandmarkPoint]:
        """
        根据指定的膝关节角和躯干倾角，精确反解 33 个关键点二维坐标
        """
        # 33 个点的默认模板
        landmarks: List[LandmarkPoint] = [
            LandmarkPoint(x=0.0, y=0.0, z=0.0, visibility=0.0, presence=0.0)
            for _ in range(33)
        ]

        if shift_out_of_frame:
            # 异常出框模式：关键点移出边界或置信度极低
            for i in range(33):
                landmarks[i] = LandmarkPoint(x=0.5, y=1.5, z=0.0, visibility=0.1, presence=0.1)
            return landmarks

        # 几何基准参数
        ankle_x, ankle_y = 0.50, 0.82
        l_tibia = 0.22
        l_femur = 0.22
        l_torso = 0.25

        # 胫骨略微前倾角 (随着下蹲加深从 5° 增加到 18°)
        depth_ratio = max(0.0, min(1.0, (170.0 - knee_angle_deg) / 85.0))
        tibia_lean_rad = math.radians(5.0 + 13.0 * depth_ratio)

        # 膝关节坐标 (相对于脚踝向上前方)
        knee_x = ankle_x + l_tibia * math.sin(tibia_lean_rad)
        knee_y = ankle_y - l_tibia * math.cos(tibia_lean_rad)

        # 脚踝相对于膝关节的向量 v_ka
        v_ka_x = ankle_x - knee_x
        v_ka_y = ankle_y - knee_y
        norm_ka = math.hypot(v_ka_x, v_ka_y)
        u_ka_x = v_ka_x / norm_ka
        u_ka_y = v_ka_y / norm_ka

        # 膝关节内角为 knee_angle_deg，则股骨向量 v_kh 与 v_ka 的夹角为 knee_angle_deg
        # 在侧视图中，脚踝在右下方，髋关节在左上方，因此 v_kh 是将 v_ka 逆时针旋转 (180° - knee_angle)
        rot_rad = math.radians(180.0 - knee_angle_deg)
        cos_r = math.cos(rot_rad)
        sin_r = math.sin(rot_rad)

        # 二维逆时针旋转: (x*cos - y*sin, x*sin + y*cos)
        u_kh_x = u_ka_x * cos_r - u_ka_y * sin_r
        u_kh_y = u_ka_x * sin_r + u_ka_y * cos_r

        hip_x = knee_x - l_femur * u_kh_x
        hip_y = knee_y - l_femur * u_kh_y

        # 躯干相对垂线 (0, -1) 的前倾角为 torso_angle_deg (向右前倾)
        torso_rad = math.radians(torso_angle_deg)
        shoulder_x = hip_x + l_torso * math.sin(torso_rad)
        shoulder_y = hip_y - l_torso * math.cos(torso_rad)

        # 填充主要关节点
        if side.upper() == "LEFT":
            indices = {"shoulder": 11, "hip": 23, "knee": 25, "ankle": 27}
        else:
            indices = {"shoulder": 12, "hip": 24, "knee": 26, "ankle": 28}

        landmarks[indices["ankle"]] = LandmarkPoint(x=ankle_x, y=ankle_y, z=0.0, visibility=visibility, presence=1.0)
        landmarks[indices["knee"]] = LandmarkPoint(x=knee_x, y=knee_y, z=0.0, visibility=visibility, presence=1.0)
        landmarks[indices["hip"]] = LandmarkPoint(x=hip_x, y=hip_y, z=0.0, visibility=visibility, presence=1.0)
        landmarks[indices["shoulder"]] = LandmarkPoint(x=shoulder_x, y=shoulder_y, z=0.0, visibility=visibility, presence=1.0)

        return landmarks

    @classmethod
    def generate_case_stream(
        cls,
        case_id: TestCaseId,
        fps: float = 30.0,
    ) -> List[Tuple[int, int, List[LandmarkPoint], bool]]:
        """
        生成指定黄金测试用例的时序帧数据流
        返回: List[(frame_index, timeline_us, landmarks, is_valid)]
        """
        dt_us = int(1e6 / fps)
        stream: List[Tuple[int, int, List[LandmarkPoint], bool]] = []
        frame_idx = 0

        def append_frame(knee: float, torso: float, valid: bool = True, out_of_frame: bool = False):
            nonlocal frame_idx
            time_us = frame_idx * dt_us
            lms = cls._create_frame_landmarks(knee, torso, shift_out_of_frame=out_of_frame)
            stream.append((frame_idx, time_us, lms, valid and not out_of_frame))
            frame_idx += 1

        if case_id == TestCaseId.TC_01_PERFECT_SQUAT:
            # 标准深蹲: min_knee ~92°, max_torso ~22°
            # 1. 站立准备 (10 帧)
            for _ in range(10):
                append_frame(170.0, 8.0)
            # 2. 下蹲 (20 帧)
            for i in range(1, 21):
                k = 170.0 - (170.0 - 92.0) * (i / 20.0)
                t = 8.0 + (22.0 - 8.0) * (i / 20.0)
                append_frame(k, t)
            # 3. 最低点停留 (8 帧)
            for _ in range(8):
                append_frame(92.0, 22.0)
            # 4. 起身 (20 帧)
            for i in range(1, 21):
                k = 92.0 + (170.0 - 92.0) * (i / 20.0)
                t = 22.0 - (22.0 - 8.0) * (i / 20.0)
                append_frame(k, t)
            # 5. 恢复站立 (10 帧)
            for _ in range(10):
                append_frame(170.0, 8.0)

        elif case_id == TestCaseId.TC_02_SHALLOW_SQUAT:
            # 浅蹲: min_knee ~108.5° (>100°), max_torso ~22°
            for _ in range(10):
                append_frame(170.0, 8.0)
            for i in range(1, 21):
                k = 170.0 - (170.0 - 108.5) * (i / 20.0)
                t = 8.0 + (22.0 - 8.0) * (i / 20.0)
                append_frame(k, t)
            for _ in range(8):
                append_frame(108.5, 22.0)
            for i in range(1, 21):
                k = 108.5 + (170.0 - 108.5) * (i / 20.0)
                t = 22.0 - (22.0 - 8.0) * (i / 20.0)
                append_frame(k, t)
            for _ in range(10):
                append_frame(170.0, 8.0)

        elif case_id == TestCaseId.TC_03_EXCESSIVE_LEAN:
            # 躯干过度前倾: min_knee ~92°, max_torso ~52.0° (>45°)
            for _ in range(10):
                append_frame(170.0, 8.0)
            for i in range(1, 21):
                k = 170.0 - (170.0 - 92.0) * (i / 20.0)
                t = 8.0 + (52.0 - 8.0) * (i / 20.0)
                append_frame(k, t)
            for _ in range(8):
                append_frame(92.0, 52.0)
            for i in range(1, 21):
                k = 92.0 + (170.0 - 92.0) * (i / 20.0)
                t = 52.0 - (52.0 - 8.0) * (i / 20.0)
                append_frame(k, t)
            for _ in range(10):
                append_frame(170.0, 8.0)

        elif case_id == TestCaseId.TC_04_DUAL_DEFECT:
            # 双缺陷: min_knee ~109.0°, max_torso ~51.0° (>45°)
            for _ in range(10):
                append_frame(170.0, 8.0)
            for i in range(1, 21):
                k = 170.0 - (170.0 - 109.0) * (i / 20.0)
                t = 8.0 + (51.0 - 8.0) * (i / 20.0)
                append_frame(k, t)
            for _ in range(8):
                append_frame(109.0, 51.0)
            for i in range(1, 21):
                k = 109.0 + (170.0 - 109.0) * (i / 20.0)
                t = 51.0 - (51.0 - 8.0) * (i / 20.0)
                append_frame(k, t)
            for _ in range(10):
                append_frame(170.0, 8.0)

        elif case_id == TestCaseId.TC_05_OUT_OF_FRAME:
            # 异常出框: 下蹲到一半 (第 25 帧起) 身体移出下边缘
            for _ in range(10):
                append_frame(170.0, 8.0)
            for i in range(1, 15):
                k = 170.0 - (170.0 - 120.0) * (i / 14.0)
                t = 8.0 + (20.0 - 8.0) * (i / 14.0)
                append_frame(k, t)
            # 突发出框 25 帧
            for _ in range(25):
                append_frame(120.0, 20.0, valid=False, out_of_frame=True)
            # 恢复站立
            for _ in range(10):
                append_frame(170.0, 8.0)

        return stream


class GoldenAssetRegistry:
    """黄金样本资产规范注册表"""

    _DEFAULT_SPECS = [
        GoldenSampleSpec(
            case_id=TestCaseId.TC_01_PERFECT_SQUAT,
            case_name="标准规范深蹲 (标杆组)",
            description="下蹲充分达标(膝角<100°)，躯干挺拔控制良好(前倾<35°)，时序完整稳定闭环",
            video_path=None,
            sha256_hash="tc01_perfect_squat_baseline_hash_v1",
            expected_count=1,
            expected_status="ACCEPTABLE",
            expected_primary_reason="ACCEPTABLE",
            expected_reason_codes=["COMPLETE_REP", "ACCEPTABLE"],
            tolerance_band=ToleranceBand(knee_min_deg=(85.0, 98.0), torso_max_deg=(15.0, 28.0)),
        ),
        GoldenSampleSpec(
            case_id=TestCaseId.TC_02_SHALLOW_SQUAT,
            case_name="下蹲深度不足 (浅蹲)",
            description="动作完整但下蹲深度不足，最低点膝关节夹角明显大于100°基准线",
            video_path=None,
            sha256_hash="tc02_shallow_squat_baseline_hash_v1",
            expected_count=1,
            expected_status="NEEDS_IMPROVEMENT",
            expected_primary_reason="INSUFFICIENT_DEPTH",
            expected_reason_codes=["COMPLETE_REP", "INSUFFICIENT_DEPTH"],
            tolerance_band=ToleranceBand(knee_min_deg=(102.0, 115.0), torso_max_deg=(15.0, 28.0)),
        ),
        GoldenSampleSpec(
            case_id=TestCaseId.TC_03_EXCESSIVE_LEAN,
            case_name="躯干过度前倾",
            description="下蹲深度达标，但在下蹲与最低点阶段躯干前倾夹角显著超过35°基准线",
            video_path=None,
            sha256_hash="tc03_excessive_lean_baseline_hash_v1",
            expected_count=1,
            expected_status="NEEDS_IMPROVEMENT",
            expected_primary_reason="EXCESSIVE_TORSO_LEAN",
            expected_reason_codes=["COMPLETE_REP", "EXCESSIVE_TORSO_LEAN"],
            tolerance_band=ToleranceBand(knee_min_deg=(85.0, 98.0), torso_max_deg=(48.0, 56.0)),
        ),
        GoldenSampleSpec(
            case_id=TestCaseId.TC_04_DUAL_DEFECT,
            case_name="复合缺陷深蹲",
            description="同时存在下蹲深度偏浅与躯干过度前倾两项质量缺陷，验证仲裁严重度排序",
            video_path=None,
            sha256_hash="tc04_dual_defect_baseline_hash_v1",
            expected_count=1,
            expected_status="NEEDS_IMPROVEMENT",
            expected_primary_reason="INSUFFICIENT_DEPTH",
            expected_reason_codes=["INSUFFICIENT_DEPTH", "EXCESSIVE_TORSO_LEAN"],
            tolerance_band=ToleranceBand(knee_min_deg=(102.0, 115.0), torso_max_deg=(48.0, 56.0)),
        ),
        GoldenSampleSpec(
            case_id=TestCaseId.TC_05_OUT_OF_FRAME,
            case_name="身体出框异常拒绝",
            description="动作中途受试者身体下部移出画幅，触发一票否决强拒绝，不予评价且不加计数",
            video_path=None,
            sha256_hash="tc05_out_of_frame_baseline_hash_v1",
            expected_count=0,
            expected_status="NOT_EVALUATED",
            expected_primary_reason="OUT_OF_FRAME",
            expected_reason_codes=["OUT_OF_FRAME", "NOT_EVALUATED"],
            tolerance_band=ToleranceBand(knee_min_deg=(0.0, 180.0), torso_max_deg=(0.0, 180.0)),
        ),
    ]

    def __init__(self, custom_specs: Optional[List[GoldenSampleSpec]] = None):
        self._specs = {s.case_id: s for s in (custom_specs or self._DEFAULT_SPECS)}

    def get_spec(self, case_id: TestCaseId) -> GoldenSampleSpec:
        if case_id not in self._specs:
            raise KeyError(f"未注册的黄金用例 ID: {case_id}")
        return self._specs[case_id]

    def list_all(self) -> List[GoldenSampleSpec]:
        return list(self._specs.values())

    def export_manifest(self, output_path: Path) -> Path:
        """导出 golden_manifest.json"""
        manifest_data = {
            "manifest_version": "1.0.0",
            "baseline_id": "P0-SQUAT-SIDE-OFFLINE-v1.0",
            "samples": [spec.to_dict() for spec in self.list_all()],
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, ensure_ascii=False, indent=2)
        return output_path
