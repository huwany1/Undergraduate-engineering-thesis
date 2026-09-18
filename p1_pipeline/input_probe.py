# -*- coding: utf-8 -*-
"""
P1 输入预检模块 (InputProbe)
依据: P1_姿态视频链路_P0级详细实施方案.md (Section 02.2 & 03.1)
"""

import hashlib
import json
import math
from pathlib import Path
from typing import Union, Dict, Any, Optional
import cv2

from .contracts import InputManifest, TimeBasis, ReasonCode


class InputProbeError(Exception):
    def __init__(self, reason_code: ReasonCode, message: str):
        super().__init__(f"[{reason_code.value}] {message}")
        self.reason_code = reason_code
        self.message = message


class InputProbe:
    """负责在解码前校验 P0 Permit、输入媒体完整性、时间基准与尺寸"""

    @staticmethod
    def calculate_sha256(file_path: Union[str, Path], chunk_size: int = 65536) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(chunk_size):
                h.update(chunk)
        return h.hexdigest()

    @classmethod
    def verify_p0_permit(cls, permit_data: Union[str, Path, Dict[str, Any]]) -> Dict[str, Any]:
        """校验 P0 准入凭证格式与时效状态"""
        if isinstance(permit_data, (str, Path)):
            permit_path = Path(permit_data)
            if not permit_path.exists():
                raise InputProbeError(
                    ReasonCode.P0_PERMIT_INVALID,
                    f"P0 Permit 文件不存在: {permit_path}"
                )
            with open(permit_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        elif isinstance(permit_data, dict):
            data = permit_data
        else:
            raise InputProbeError(
                ReasonCode.P0_PERMIT_INVALID,
                f"不支持的 Permit 数据类型: {type(permit_data)}"
            )

        # 检查 baseline_id
        baseline_id = data.get("baseline_id")
        if not baseline_id or "P0-SQUAT" not in baseline_id:
            raise InputProbeError(
                ReasonCode.P0_PERMIT_INVALID,
                f"baseline_id 无效或缺失: {baseline_id}"
            )

        # 检查 runtime_permit
        runtime_permit = data.get("runtime_permit", {})
        permit_id = runtime_permit.get("processing_permit_id")
        if not permit_id:
            raise InputProbeError(
                ReasonCode.P0_PERMIT_INVALID,
                "runtime_permit 缺失 processing_permit_id"
            )

        disposal_status = runtime_permit.get("disposal_status")
        if disposal_status != "ACTIVE_HOLD":
            raise InputProbeError(
                ReasonCode.P0_PERMIT_INVALID,
                f"Permit 处置状态非 ACTIVE_HOLD: {disposal_status}"
            )

        # 检查准入状态
        adm_status = data.get("admission_status", {})
        if adm_status.get("quality_status") != "ADMITTED":
            raise InputProbeError(
                ReasonCode.P0_PERMIT_INVALID,
                f"视频未被 P0 准入 (quality_status: {adm_status.get('quality_status')})"
            )

        return data

    @classmethod
    def probe(
        cls,
        video_path: Union[str, Path],
        permit_data: Union[str, Path, Dict[str, Any]],
        time_basis: TimeBasis = TimeBasis.DERIVED_CFR_NONRELEASE
    ) -> InputManifest:
        """完整预检流程"""
        v_path = Path(video_path)
        if not v_path.exists():
            raise InputProbeError(
                ReasonCode.INPUT_NOT_FOUND,
                f"输入视频文件未找到: {v_path}"
            )

        # 1. 验证 P0 Permit
        permit_info = cls.verify_p0_permit(permit_data)
        permit_id = permit_info["runtime_permit"]["processing_permit_id"]
        camera_id = permit_info.get("capture_audit", {}).get("camera_profile_id")

        # 2. 计算视频哈希
        video_sha256 = cls.calculate_sha256(v_path)

        # 3. 探查视频流容器元数据
        cap = cv2.VideoCapture(str(v_path))
        if not cap.isOpened():
            raise InputProbeError(
                ReasonCode.UNSUPPORTED_CONTAINER,
                f"OpenCV 无法打开视频容器: {v_path}"
            )

        try:
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            if width <= 0 or height <= 0:
                raise InputProbeError(
                    ReasonCode.UNSUPPORTED_CONTAINER,
                    f"无效的视频分辨率: {width}x{height}"
                )

            if fps <= 0.0 or math.isnan(fps):
                raise InputProbeError(
                    ReasonCode.FPS_UNAVAILABLE,
                    f"视频 FPS 无效或不可读: {fps}"
                )

            if total_frames <= 0:
                raise InputProbeError(
                    ReasonCode.NO_DECODABLE_FRAMES,
                    f"视频总帧数非正数: {total_frames}"
                )

            return InputManifest(
                video_path=str(v_path.resolve()),
                video_sha256=video_sha256,
                width=width,
                height=height,
                fps=fps,
                frame_count_est=total_frames,
                permit_id=permit_id,
                time_basis=time_basis,
                camera_profile_id=camera_id,
            )
        finally:
            cap.release()
