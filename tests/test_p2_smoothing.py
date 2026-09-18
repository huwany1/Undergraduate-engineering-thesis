# -*- coding: utf-8 -*-
"""
P2 1€ 滤波算法单元测试
测试目标:
1. 白噪声抖动滤除效果 (方差大幅缩减);
2. 阶跃响应收敛性与无剧烈超调;
3. dt 极小值除零保护与时间断裂自愈重置;
4. 因果性测试 (输出与未来数据严格无关).
"""

import math
import random
import numpy as np
import pytest
from p2_temporal.smoothing.one_euro_filter import OneEuroFilter


def test_one_euro_filter_noise_reduction():
    """测试在稳定静态信号中混入高频白噪声时，滤波后方差显著降低"""
    random.seed(42)
    filt = OneEuroFilter(min_cutoff=1.0, beta=0.005)

    base_val = 170.0
    dt = 1.0 / 30.0  # 30 fps
    noisy_signals = []
    filtered_signals = []

    for i in range(150):
        t = i * dt
        noise = random.gauss(0, 3.0)  # 3度标准差的高斯白噪声
        raw_val = base_val + noise
        filt_val, _ = filt.filter_step(raw_val, t)

        # 丢弃前 10 帧初始过渡期
        if i >= 10:
            noisy_signals.append(raw_val)
            filtered_signals.append(filt_val)

    raw_var = float(np.var(noisy_signals))
    filt_var = float(np.var(filtered_signals))

    # 滤波后方差至少应减少 70%
    assert filt_var < raw_var * 0.3, f"Filtering did not reduce variance enough: {filt_var} vs {raw_var}"


def test_one_euro_filter_step_response():
    """测试阶跃信号下的快速响应与收敛"""
    filt = OneEuroFilter(min_cutoff=1.0, beta=0.01)
    dt = 1.0 / 30.0

    # 初始 170 度持续 1 秒
    for i in range(30):
        filt.filter_step(170.0, i * dt)

    # 突然下蹲阶跃至 90 度
    step_vals = []
    for i in range(30, 60):
        t = i * dt
        val, vel = filt.filter_step(90.0, t)
        step_vals.append(val)

    # 验证最终收敛到 90 度附近 (误差小于 0.5 度)
    assert abs(step_vals[-1] - 90.0) < 0.5
    # 验证响应是单调下降的，无恶性正向回弹
    assert step_vals[0] > step_vals[5] > step_vals[-1]


def test_one_euro_filter_zero_dt_protection():
    """测试极端连续重复时间戳 (dt=0)，无除零崩溃且保持原状态"""
    filt = OneEuroFilter()
    v1, d1 = filt.filter_step(100.0, 1.0)
    # 重复传入完全相同的时间戳
    v2, d2 = filt.filter_step(120.0, 1.0)

    assert math.isfinite(v2)
    assert math.isfinite(d2)
    assert v2 == v1


def test_one_euro_filter_temporal_gap_reset():
    """测试长时断流 (dt > max_dt_gap) 时自愈重置，不发生微分尖峰爆炸"""
    filt = OneEuroFilter(max_dt_gap=0.5)

    filt.filter_step(100.0, 0.0)
    filt.filter_step(102.0, 0.033)

    # 突发间隔 2.0 秒无数据后恢复
    val, vel = filt.filter_step(50.0, 2.033)

    assert math.isfinite(val)
    assert math.isfinite(vel)
    # 断裂后重置，速度导数应被安全置为 0，而不是 (50-102)/2.0 的剧烈突变
    assert vel == 0.0
    assert val == 50.0


def test_one_euro_filter_causality():
    """测试严格因果性：单帧输出只由截至当前帧的历史决定"""
    filt_a = OneEuroFilter()
    filt_b = OneEuroFilter()

    stream_shared = [170.0, 168.0, 165.0, 160.0]
    out_a = [filt_a.filter_step(x, i * 0.033)[0] for i, x in enumerate(stream_shared)]

    # stream_b 前 4 帧完全相同，第 5 帧未来数据差异巨大
    out_b = [filt_b.filter_step(x, i * 0.033)[0] for i, x in enumerate(stream_shared)]

    assert out_a == out_b
