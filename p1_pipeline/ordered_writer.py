# -*- coding: utf-8 -*-
"""
P1 严格保序视频写入器 (OrderedWriter)
依据: P1_姿态视频链路_P0级详细实施方案.md (Section 03.1, 05.1 & 08.1)
"""

from pathlib import Path
from typing import Union, Optional
import cv2
import numpy as np

from .contracts import ReasonCode


class OrderedWriterError(Exception):
    def __init__(self, reason_code: ReasonCode, message: str):
        super().__init__(f"[{reason_code.value}] {message}")
        self.reason_code = reason_code
        self.message = message


class OrderedWriter:
    """按权威连续帧序写出视频，任何乱序、跳帧或重复帧立即触发熔断"""

    def __init__(
        self,
        output_video_path: Union[str, Path],
        width: int,
        height: int,
        fps: float,
        fourcc_str: str = "mp4v"
    ):
        self.output_path = Path(output_video_path)
        self.width = width
        self.height = height
        self.fps = fps
        self.fourcc_str = fourcc_str
        self.next_expected_index = 0
        self.written_count = 0
        self.writer: Optional[cv2.VideoWriter] = None

        self._init_writer()

    def _init_writer(self) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        fourcc = cv2.VideoWriter_fourcc(*self.fourcc_str)
        self.writer = cv2.VideoWriter(
            str(self.output_path),
            fourcc,
            self.fps,
            (self.width, self.height)
        )
        if not self.writer.isOpened():
            raise OrderedWriterError(
                ReasonCode.OUTPUT_CODEC_UNAVAILABLE,
                f"无法初始化 VideoWriter (编码器: {self.fourcc_str}, 目标: {self.output_path})"
            )

    def write_frame(self, frame_index: int, rendered_bgr: np.ndarray) -> None:
        # 严格单调连续校验
        if frame_index != self.next_expected_index:
            raise OrderedWriterError(
                ReasonCode.INTERNAL_ORDER_VIOLATION,
                f"帧序违约！期望接收 frame_index={self.next_expected_index}, 实际收到 frame_index={frame_index}"
            )

        if self.writer is None or not self.writer.isOpened():
            raise OrderedWriterError(
                ReasonCode.OUTPUT_WRITE_FAILED,
                "VideoWriter 句柄已关闭或不可写"
            )

        # 尺寸对齐检查
        h, w = rendered_bgr.shape[:2]
        if w != self.width or h != self.height:
            raise OrderedWriterError(
                ReasonCode.OUTPUT_WRITE_FAILED,
                f"帧尺寸不匹配: 期望 {self.width}x{self.height}, 实际 {w}x{h}"
            )

        self.writer.write(rendered_bgr)
        self.written_count += 1
        self.next_expected_index += 1

    def close(self) -> None:
        if self.writer is not None:
            self.writer.release()
            self.writer = None
