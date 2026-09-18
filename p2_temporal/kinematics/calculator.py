# -*- coding: utf-8 -*-
"""
2D 屏幕空间运动学特征计算器
依据: P2_时序闭环_详细实施方案.md (Section 06)
包含:
1. 膝关节弯曲夹角 (Knee Angle)
2. 躯干前倾夹角 (Torso Angle)
3. 归一化髋部垂直位移 (Normalized Hip Y Displacement)
4. 数值安全截断与除零退化防护
"""

import math
from typing import Dict, Any, Optional, Tuple, Sequence
import numpy as np


class KinematicsCalculator:
    # MediaPipe 33 关键点标准索引定义
    JOINT_INDICES = {
        "LEFT": {
            "shoulder": 11,
            "hip": 23,
            "knee": 25,
            "ankle": 27,
        },
        "RIGHT": {
            "shoulder": 12,
            "hip": 24,
            "knee": 26,
            "ankle": 28,
        },
    }

    EPSILON = 1e-7

    def __init__(self):
        self.standing_hip_y: Optional[float] = None
        self.standing_thigh_length: Optional[float] = None

    def reset_baseline(self) -> None:
        """重置站立基线校准值"""
        self.standing_hip_y = None
        self.standing_thigh_length = None

    @classmethod
    def calculate_angle_3points(
        cls,
        p_a: Tuple[float, float],
        p_b: Tuple[float, float],
        p_c: Tuple[float, float],
    ) -> Tuple[float, bool]:
        """
        计算三点形成的空间夹角 ABC (以点 B 为顶点, 向量 BA 与 BC 的夹角)
        :param p_a: 点 A (x, y)
        :param p_b: 点 B 顶点 (x, y)
        :param p_c: 点 C (x, y)
        :return: (角度度数[0, 180], 是否计算有效无退化)
        """
        v_ba = (p_a[0] - p_b[0], p_a[1] - p_b[1])
        v_bc = (p_c[0] - p_b[0], p_c[1] - p_b[1])

        norm_ba = math.hypot(v_ba[0], v_ba[1])
        norm_bc = math.hypot(v_bc[0], v_bc[1])

        # 退化几何保护: 任意肢体长度接近零
        if norm_ba < cls.EPSILON or norm_bc < cls.EPSILON:
            return 180.0, False

        dot_product = v_ba[0] * v_bc[0] + v_ba[1] * v_bc[1]
        cos_theta = dot_product / (norm_ba * norm_bc)

        # 严格反余弦越界截断，消除浮点误差导致 NaN
        cos_theta = max(-1.0, min(1.0, cos_theta))
        angle_rad = math.acos(cos_theta)
        return math.degrees(angle_rad), True

    @classmethod
    def calculate_torso_angle(
        cls,
        p_hip: Tuple[float, float],
        p_shoulder: Tuple[float, float],
    ) -> Tuple[float, bool]:
        """
        计算躯干相对于垂直向上基准方向的倾角 (度数)
        屏幕图像坐标系: x 向右, y 向下.
        垂直向上向量为 (0, -1).
        :return: (躯干前倾角度数[0, 180], 是否有效)
        """
        v_hs = (p_shoulder[0] - p_hip[0], p_shoulder[1] - p_hip[1])
        norm_hs = math.hypot(v_hs[0], v_hs[1])

        if norm_hs < cls.EPSILON:
            return 0.0, False

        # v_vertical = (0, -1) -> dot = v_hs[0]*0 + v_hs[1]*(-1) = -v_hs[1]
        dot_product = -v_hs[1]
        cos_theta = dot_product / norm_hs
        cos_theta = max(-1.0, min(1.0, cos_theta))
        angle_rad = math.acos(cos_theta)
        return math.degrees(angle_rad), True

    def extract_features(
        self,
        landmarks: Sequence[Any],
        side: str = "LEFT",
    ) -> Tuple[float, float, float, bool]:
        """
        从一帧的姿态关键点列表中提取核心运动学标量
        :param landmarks: 长度为 33 的关键点序列，每个元素支持 .x/.y 或 ['x']/['y']
        :param side: 'LEFT' 或 'RIGHT'
        :return: (raw_knee_angle, raw_torso_angle, hip_y_norm, is_valid)
        """
        side_key = "LEFT" if side.upper().startswith("LEFT") else "RIGHT"
        indices = self.JOINT_INDICES[side_key]

        if len(landmarks) < 33:
            return 180.0, 0.0, 0.0, False

        def get_xy(idx: int) -> Tuple[float, float]:
            item = landmarks[idx]
            if hasattr(item, "x") and hasattr(item, "y"):
                return float(item.x), float(item.y)
            elif isinstance(item, dict):
                return float(item["x"]), float(item["y"])
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                return float(item[0]), float(item[1])
            raise ValueError(f"Unsupported landmark item format at index {idx}: {type(item)}")

        try:
            shoulder = get_xy(indices["shoulder"])
            hip = get_xy(indices["hip"])
            knee = get_xy(indices["knee"])
            ankle = get_xy(indices["ankle"])
        except Exception:
            return 180.0, 0.0, 0.0, False

        # 检查是否全部有限值
        all_pts = [shoulder, hip, knee, ankle]
        if not all(math.isfinite(x) and math.isfinite(y) for x, y in all_pts):
            return 180.0, 0.0, 0.0, False

        # 1. 膝关节角度 (以 knee 为顶点, hip-knee 与 ankle-knee 的夹角)
        knee_angle, knee_ok = self.calculate_angle_3points(hip, knee, ankle)

        # 2. 躯干前倾角度 (hip 到 shoulder 连线与垂直向上的夹角)
        torso_angle, torso_ok = self.calculate_torso_angle(hip, shoulder)

        # 3. 归一化髋部纵向位移
        thigh_len = math.hypot(hip[0] - knee[0], hip[1] - knee[1])
        if self.standing_thigh_length is None or self.standing_thigh_length < self.EPSILON:
            if thigh_len > self.EPSILON:
                self.standing_thigh_length = thigh_len
                self.standing_hip_y = hip[1]

        if self.standing_hip_y is not None and self.standing_thigh_length and self.standing_thigh_length > self.EPSILON:
            hip_y_norm = (hip[1] - self.standing_hip_y) / self.standing_thigh_length
        else:
            hip_y_norm = 0.0

        is_valid = knee_ok and torso_ok
        return knee_angle, torso_angle, hip_y_norm, is_valid
