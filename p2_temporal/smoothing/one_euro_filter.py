# -*- coding: utf-8 -*-
"""
1€ (One-Euro) 自适应低通滤波器
依据: Casiez et al. (CHI 2012) 及 P2_时序闭环_详细实施方案.md (Section 07)
特性:
1. 基于信号一阶微分自适应动态调整截止频率（低速大滤波消抖，高速高频宽降滞后）；
2. 纯因果算法（Causal），不依赖未来帧；
3. 内置 dt 极小值防护（除零保护）与时间断裂自愈重置（Temporal Gap Recovery）。
"""

import math
from typing import Tuple, Optional


class OneEuroFilter:
    def __init__(
        self,
        min_cutoff: float = 1.0,
        beta: float = 0.005,
        d_cutoff: float = 1.0,
        min_dt: float = 1e-4,
        max_dt_gap: float = 0.5,
    ):
        """
        :param min_cutoff: 最小低通截止频率 (Hz)，控制静止低速时的平滑程度
        :param beta: 速度响应增益系数，控制高速运动时的灵敏度与延迟抑制
        :param d_cutoff: 导数低通滤波截止频率 (Hz)，通常设为 1.0 Hz
        :param min_dt: 时间间隔下限保护 (s)，避免除以极小值或零
        :param max_dt_gap: 允许的最大时间跳跃阈值 (s)，超过则判定为断流并重置
        """
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)
        self.min_dt = float(min_dt)
        self.max_dt_gap = float(max_dt_gap)

        self.prev_x: Optional[float] = None
        self.prev_dx: float = 0.0
        self.prev_timestamp: Optional[float] = None

    def reset(self) -> None:
        """重置内部滤波状态"""
        self.prev_x = None
        self.prev_dx = 0.0
        self.prev_timestamp = None

    @staticmethod
    def _alpha(dt: float, cutoff: float) -> float:
        """计算低通滤波器加权因子 alpha"""
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    @staticmethod
    def _lowpass(x: float, prev_x: float, alpha: float) -> float:
        """标准一阶指数低通滤波"""
        return alpha * x + (1.0 - alpha) * prev_x

    def filter_step(self, x: float, timestamp_s: float) -> Tuple[float, float]:
        """
        输入当前测量值与时间戳 (单位: 秒)，返回 (平滑后的数值, 平滑后的一阶导数)
        """
        x = float(x)
        timestamp_s = float(timestamp_s)

        # 首帧冷启动
        if self.prev_timestamp is None or self.prev_x is None:
            self.prev_x = x
            self.prev_dx = 0.0
            self.prev_timestamp = timestamp_s
            return x, 0.0

        dt = timestamp_s - self.prev_timestamp

        # 防御 1: 时间倒退或间隔极小 (小于 0.1ms)，阻断除零爆炸，保持原状态
        if dt < self.min_dt:
            return self.prev_x, self.prev_dx

        # 防御 2: 时间跳跃/断裂 (超过阈值)，判定为时序不连续，冷启动重置
        if dt > self.max_dt_gap:
            self.prev_x = x
            self.prev_dx = 0.0
            self.prev_timestamp = timestamp_s
            return x, 0.0

        # 1. 计算当前原始微分与滤波后的一阶导数 (dx)
        raw_dx = (x - self.prev_x) / dt
        alpha_d = self._alpha(dt, self.d_cutoff)
        filtered_dx = self._lowpass(raw_dx, self.prev_dx, alpha_d)

        # 2. 依据速度变化率自适应调制主截止频率 fc
        cutoff = self.min_cutoff + self.beta * abs(filtered_dx)

        # 3. 滤波主信号
        alpha = self._alpha(dt, cutoff)
        filtered_x = self._lowpass(x, self.prev_x, alpha)

        # 更新历史状态
        self.prev_x = filtered_x
        self.prev_dx = filtered_dx
        self.prev_timestamp = timestamp_s

        return filtered_x, filtered_dx
