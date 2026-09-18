# -*- coding: utf-8 -*-
"""
P1 顺序解码适配器 (DecodeAdapter)
依据: P1_姿态视频链路_P0级详细实施方案.md (Section 03.1 & 04.2)
"""

from pathlib import Path
from typing import Generator, Union, Optional
import cv2
import numpy as np

from .contracts import FrameEnvelope, TimeBasis, ReasonCode


class DecodeAdapterError(Exception):
    def __init__(self, reason_code: ReasonCode, message: str):
        super().__init__(f"[{reason_code.value}] {message}")
        self.reason_code = reason_code
        self.message = message


class DecodeAdapter:
    """顺序解码视频帧，构建携带时间戳与严格单调序列的 FrameEnvelope"""

    def __init__(
        self,
        video_path: Union[str, Path],
        run_id: str,
        fps: float,
        time_basis: TimeBasis = TimeBasis.DERIVED_CFR_NONRELEASE
    ):
        self.video_path = Path(video_path)
        self.run_id = run_id
        self.fps = fps
        self.time_basis = time_basis
        self.last_timeline_us: Optional[int] = None
        self.current_frame_index = 0

    def iterate_frames(self) -> Generator[FrameEnvelope, None, None]:
        cap = cv2.VideoCapture(str(self.video_path))
        if not cap.isOpened():
            raise DecodeAdapterError(
                ReasonCode.UNSUPPORTED_CONTAINER,
                f"无法打开视频源进行解码: {self.video_path}"
            )

        try:
            while True:
                ret, frame_bgr = cap.read()
                if not ret or frame_bgr is None:
                    # 正常读取结束（或空流）
                    break

                height, width = frame_bgr.shape[:2]

                # 计算 timeline_us
                if self.time_basis == TimeBasis.DERIVED_CFR_NONRELEASE:
                    # 推导微秒时间戳 (每帧 1e6 / fps)
                    timeline_us = int(round((self.current_frame_index / self.fps) * 1_000_000))
                else:
                    # 使用 PTS 毫秒属性转微秒
                    pos_msec = cap.get(cv2.CAP_PROP_POS_MSEC)
                    timeline_us = int(round(pos_msec * 1000))

                # 严格时间戳递增检查
                if self.last_timeline_us is not None and timeline_us <= self.last_timeline_us:
                    raise DecodeAdapterError(
                        ReasonCode.PTS_NON_MONOTONIC,
                        f"帧 {self.current_frame_index} 时间戳未严格单调递增 "
                        f"({timeline_us} us <= {self.last_timeline_us} us)"
                    )
                self.last_timeline_us = timeline_us

                # 色彩空间单次转换 BGR -> RGB
                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

                envelope = FrameEnvelope(
                    run_id=self.run_id,
                    frame_index=self.current_frame_index,
                    timeline_us=timeline_us,
                    decoded_bgr=frame_bgr,
                    decoded_rgb=frame_rgb,
                    width=width,
                    height=height,
                    rotation_applied=0,
                    decode_status="OK",
                    source_pts=timeline_us if self.time_basis != TimeBasis.DERIVED_CFR_NONRELEASE else None,
                    time_base=self.time_basis.value,
                )

                yield envelope
                self.current_frame_index += 1

            if self.current_frame_index == 0:
                raise DecodeAdapterError(
                    ReasonCode.NO_DECODABLE_FRAMES,
                    f"视频未成功解码出任何有效帧: {self.video_path}"
                )

        finally:
            cap.release()
