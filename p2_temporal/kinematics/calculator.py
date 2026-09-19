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
            "heel": 29,
            "foot_index": 31,
        },
        "RIGHT": {
            "shoulder": 12,
            "hip": 24,
            "knee": 26,
            "ankle": 28,
            "heel": 30,
            "foot_index": 32,
        },
    }

    EPSILON = 1e-7

    def __init__(self):
        self.standing_hip_y: Optional[float] = None
        self.standing_thigh_length: Optional[float] = None
        self.standing_heel_pitch: Optional[float] = None

    def reset_baseline(self) -> None:
        """重置站立基线校准值"""
        self.standing_hip_y = None
        self.standing_thigh_length = None
        self.standing_heel_pitch = None

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

    def extract_extended_biomechanics(
        self,
        landmarks: Sequence[Any],
        side: str = "LEFT",
        current_torso_angle: float = 0.0,
    ) -> Dict[str, Any]:
        """
        提取四大伤病隐患运动学生物力学特征:
        1. 膝关节内扣比率 (valgus_ratio, 需双侧正面/半侧可见)
        2. 脚跟离地抬起俯仰角 (heel_lift_deg)
        3. 骨盆翻转角度 (pelvic_tilt_deg)
        4. 左右双腿不对称差 (bilateral_knee_diff, 需双侧可见)
        """
        res: Dict[str, Any] = {
            "valgus_ratio": None,
            "heel_lift_deg": 0.0,
            "pelvic_tilt_deg": 0.0,
            "bilateral_knee_diff": None,
            "is_frontal_observable": False,
        }

        if len(landmarks) < 33:
            return res

        def get_pt_vis(idx: int) -> Tuple[float, float, float]:
            item = landmarks[idx]
            vis = 1.0
            if hasattr(item, "x") and hasattr(item, "y"):
                vis = getattr(item, "visibility", 1.0) or 1.0
                return float(item.x), float(item.y), float(vis)
            elif isinstance(item, dict):
                vis = item.get("visibility", 1.0)
                if vis is None:
                    vis = 1.0
                return float(item["x"]), float(item["y"]), float(vis)
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                vis = float(item[2]) if len(item) >= 3 and item[2] is not None else 1.0
                return float(item[0]), float(item[1]), float(vis)
            return 0.0, 0.0, 0.0

        try:
            l_hip_x, l_hip_y, l_hip_v = get_pt_vis(23)
            r_hip_x, r_hip_y, r_hip_v = get_pt_vis(24)
            l_knee_x, l_knee_y, l_knee_v = get_pt_vis(25)
            r_knee_x, r_knee_y, r_knee_v = get_pt_vis(26)
            l_ankle_x, l_ankle_y, l_ankle_v = get_pt_vis(27)
            r_ankle_x, r_ankle_y, r_ankle_v = get_pt_vis(28)
            l_heel_x, l_heel_y, _ = get_pt_vis(29)
            r_heel_x, r_heel_y, _ = get_pt_vis(30)
            l_toe_x, l_toe_y, _ = get_pt_vis(31)
            r_toe_x, r_toe_y, _ = get_pt_vis(32)
        except Exception:
            return res

        side_key = "LEFT" if side.upper().startswith("LEFT") else "RIGHT"

        # 1. 脚跟离地计算 (Heel Lift)
        heel_x, heel_y = (l_heel_x, l_heel_y) if side_key == "LEFT" else (r_heel_x, r_heel_y)
        toe_x, toe_y = (l_toe_x, l_toe_y) if side_key == "LEFT" else (r_toe_x, r_toe_y)

        dx = abs(toe_x - heel_x)
        # 屏幕图像坐标系 y 向下: 若脚后跟抬起，heel_y 向上变小，toe_y - heel_y 变大
        dy = toe_y - heel_y
        pitch_deg = math.degrees(math.atan2(dy, dx + self.EPSILON))

        if self.standing_heel_pitch is None:
            self.standing_heel_pitch = pitch_deg

        heel_lift = max(0.0, pitch_deg - self.standing_heel_pitch)
        res["heel_lift_deg"] = round(heel_lift, 2)

        # 2. 骨盆翻转计算 (Pelvic Tilt / Butt Wink)
        hip_x = l_hip_x if side_key == "LEFT" else r_hip_x
        hip_y = l_hip_y if side_key == "LEFT" else r_hip_y
        knee_x = l_knee_x if side_key == "LEFT" else r_knee_x
        knee_y = l_knee_y if side_key == "LEFT" else r_knee_y

        thigh_dx = knee_x - hip_x
        thigh_dy = knee_y - hip_y
        thigh_angle = math.degrees(math.atan2(abs(thigh_dy), abs(thigh_dx) + self.EPSILON))
        # 当大腿趋于水平甚至下探时，躯干角与大腿角不匹配且反折时计算骨盆卷折
        pelvic_dev = max(0.0, current_torso_angle - thigh_angle - 25.0)
        res["pelvic_tilt_deg"] = round(pelvic_dev, 2)

        # 3. 视点可观测性判断 (Frontal / Semi-frontal vs Pure Sagittal)
        hip_w = math.hypot(l_hip_x - r_hip_x, l_hip_y - r_hip_y)
        thigh_ref = self.standing_thigh_length or 0.25
        min_both_vis = min(l_knee_v, r_knee_v, l_ankle_v, r_ankle_v)

        # 需双侧可见且非绝对单侧侧视遮挡
        if min_both_vis >= 0.5 and hip_w >= (0.12 * thigh_ref):
            res["is_frontal_observable"] = True

            # 膝关节内扣比率: 双膝宽度 / 双踝宽度
            knee_w = math.hypot(l_knee_x - r_knee_x, l_knee_y - r_knee_y)
            ankle_w = math.hypot(l_ankle_x - r_ankle_x, l_ankle_y - r_ankle_y)
            if ankle_w > self.EPSILON:
                valgus_r = knee_w / ankle_w
                res["valgus_ratio"] = round(valgus_r, 3)

            # 动作双侧不对称: 左右膝屈曲角差值
            l_knee_ang, l_ok = self.calculate_angle_3points((l_hip_x, l_hip_y), (l_knee_x, l_knee_y), (l_ankle_x, l_ankle_y))
            r_knee_ang, r_ok = self.calculate_angle_3points((r_hip_x, r_hip_y), (r_knee_x, r_knee_y), (r_ankle_x, r_ankle_y))
            if l_ok and r_ok:
                res["bilateral_knee_diff"] = round(abs(l_knee_ang - r_knee_ang), 2)

        return res
