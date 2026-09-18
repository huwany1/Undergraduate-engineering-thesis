# -*- coding: utf-8 -*-
"""
确定性测试姿态引擎 (DeterministicMockPoseEngine)
用于在无外部大模型文件或离线 CI 环境下进行确定性回归与故障注入测试
"""

from typing import Dict, Any, Optional, Set, List
import numpy as np

from .base import PoseEngine
from ..contracts import (
    PoseFrameResult,
    LandmarkPoint,
    ProcessingStatus,
    PoseStatus,
)


class DeterministicMockPoseEngine(PoseEngine):
    """离线确定性姿态引擎"""

    def __init__(
        self,
        no_pose_indices: Optional[Set[int]] = None,
        out_of_frame_indices: Optional[Dict[int, int]] = None,  # frame_idx -> landmark_idx
        low_visibility_indices: Optional[Dict[int, int]] = None, # frame_idx -> landmark_idx
        simulate_side: str = "LEFT",
    ):
        self.no_pose_indices = no_pose_indices or set()
        self.out_of_frame_indices = out_of_frame_indices or {}
        self.low_visibility_indices = low_visibility_indices or {}
        self.simulate_side = simulate_side
        self.frame_counter = 0

    def initialize(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.frame_counter = 0

    def _generate_synthetic_landmarks(self, frame_idx: int) -> List[LandmarkPoint]:
        """生成一组标准的 33 点归一化侧视姿态关键点"""
        landmarks = []
        is_left = (self.simulate_side == "LEFT")

        # 基础坐标（归一化 0.0 - 1.0）
        for idx in range(33):
            # 默认可见度：主侧较高(0.9)，对侧稍低(0.4)
            vis = 0.9 if (is_left and idx % 2 != 0) or (not is_left and idx % 2 == 0) else 0.4
            pres = 0.95

            # 模拟头部 (0-10)
            if idx <= 10:
                x, y, z = 0.5, 0.15 + (idx * 0.005), 0.0
            # 模拟躯干与上肢 (11-22)
            elif 11 <= idx <= 22:
                x, y, z = 0.5, 0.35 + ((idx - 11) * 0.015), 0.0
            # 模拟臀部与下肢 (23-32)
            else:
                x, y, z = 0.5, 0.60 + ((idx - 23) * 0.035), 0.0

            # 注入指定帧的异常
            if frame_idx in self.out_of_frame_indices and self.out_of_frame_indices[frame_idx] == idx:
                x, y = 1.5, 2.0  # 越界

            if frame_idx in self.low_visibility_indices and self.low_visibility_indices[frame_idx] == idx:
                vis = 0.1  # 低可见度

            landmarks.append(
                LandmarkPoint(
                    x=x,
                    y=y,
                    z=z,
                    visibility=vis,
                    presence=pres,
                )
            )

        return landmarks

    def infer_frame(self, rgb_image: np.ndarray, timestamp_us: int) -> PoseFrameResult:
        frame_idx = self.frame_counter
        self.frame_counter += 1

        if frame_idx in self.no_pose_indices:
            return PoseFrameResult(
                processing_status=ProcessingStatus.OK,
                pose_status=PoseStatus.NO_POSE,
                landmarks_2d=[],
            )

        landmarks_2d = self._generate_synthetic_landmarks(frame_idx)
        return PoseFrameResult(
            processing_status=ProcessingStatus.OK,
            pose_status=PoseStatus.POSE_DETECTED,
            landmarks_2d=landmarks_2d,
        )

    def close(self) -> None:
        pass
