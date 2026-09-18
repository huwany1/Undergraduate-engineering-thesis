# -*- coding: utf-8 -*-
"""
P2 运动学特征提取与几何数值安全测试
"""

import math
import pytest
from p2_temporal.kinematics.calculator import KinematicsCalculator


def test_calculate_angle_3points_standard():
    """测试标准三点角度计算几何精度"""
    # 直角三角形: B=(0,0), A=(0,1), C=(1,0) -> 90度
    angle, ok = KinematicsCalculator.calculate_angle_3points((0.0, 1.0), (0.0, 0.0), (1.0, 0.0))
    assert ok is True
    assert pytest.approx(angle, 1e-4) == 90.0

    # 一条直线平角: A=(0,-1), B=(0,0), C=(0,1) -> 180度
    angle_180, ok_180 = KinematicsCalculator.calculate_angle_3points((0.0, -1.0), (0.0, 0.0), (0.0, 1.0))
    assert ok_180 is True
    assert pytest.approx(angle_180, 1e-4) == 180.0


def test_calculate_torso_angle_standard():
    """测试躯干前倾角计算: 笔直竖立 vs 前倾 45 度"""
    # 竖立: Hip=(0.5, 0.5), Shoulder=(0.5, 0.2) (y 较小即在上方) -> 0 度
    angle_straight, ok = KinematicsCalculator.calculate_torso_angle((0.5, 0.5), (0.5, 0.2))
    assert ok is True
    assert pytest.approx(angle_straight, 1e-4) == 0.0

    # 前倾 45 度: Shoulder 在左上方或右上方 45 度
    angle_lean, ok_lean = KinematicsCalculator.calculate_torso_angle((0.5, 0.5), (0.7, 0.3))
    assert ok_lean is True
    assert pytest.approx(angle_lean, 1e-4) == 45.0


def test_kinematics_degenerate_zero_vector():
    """测试当两点重合时 (模长接近 0)，触发退化保护，安全返回 180度且 ok=False，绝不抛 ZeroDivisionError"""
    angle, ok = KinematicsCalculator.calculate_angle_3points((0.5, 0.5), (0.5, 0.5), (0.6, 0.7))
    assert ok is False
    assert angle == 180.0

    torso_angle, torso_ok = KinematicsCalculator.calculate_torso_angle((0.5, 0.5), (0.5, 0.5))
    assert torso_ok is False
    assert torso_angle == 0.0


def test_kinematics_extract_features_full():
    """测试基于完整 33 关键点列表提取运动学特征"""
    calc = KinematicsCalculator()

    # 构建 33 个虚拟关键点 (以 LEFT 侧为例: 11=Shoulder, 23=Hip, 25=Knee, 27=Ankle)
    landmarks = [{"x": 0.5, "y": 0.5} for _ in range(33)]

    # 设为站姿: Shoulder=(0.5, 0.2), Hip=(0.5, 0.5), Knee=(0.5, 0.7), Ankle=(0.5, 0.9)
    landmarks[11] = {"x": 0.5, "y": 0.2}  # L Shoulder
    landmarks[23] = {"x": 0.5, "y": 0.5}  # L Hip
    landmarks[25] = {"x": 0.5, "y": 0.7}  # L Knee
    landmarks[27] = {"x": 0.5, "y": 0.9}  # L Ankle

    knee_angle, torso_angle, hip_y_norm, is_valid = calc.extract_features(landmarks, side="LEFT")

    assert is_valid is True
    assert pytest.approx(knee_angle, 0.5) == 180.0
    assert pytest.approx(torso_angle, 0.5) == 0.0
    assert pytest.approx(hip_y_norm, 0.01) == 0.0
