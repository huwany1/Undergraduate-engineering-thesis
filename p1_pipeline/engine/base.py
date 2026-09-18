# -*- coding: utf-8 -*-
"""
P1 姿态引擎端口抽象基类
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import numpy as np

from ..contracts import PoseFrameResult


class PoseEngine(ABC):
    """姿态估计引擎抽象端口，严格隔离算法框架内部对象"""

    @abstractmethod
    def initialize(self, config: Optional[Dict[str, Any]] = None) -> None:
        """初始化引擎并加载模型资产"""
        pass

    @abstractmethod
    def infer_frame(self, rgb_image: np.ndarray, timestamp_us: int) -> PoseFrameResult:
        """对单帧 RGB 图像与微秒时间戳执行推理，产出中立 DTO"""
        pass

    @abstractmethod
    def close(self) -> None:
        """释放资源与底层句柄"""
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
