# -*- coding: utf-8 -*-
"""
MediaPipe Tasks PoseLandmarker (RunningMode.VIDEO) 适配器
依据: P1_姿态视频链路_P0级详细实施方案.md (Section 02.1 & 04.3)
"""

import hashlib
from pathlib import Path
from typing import Dict, Any, Optional
import numpy as np

from .base import PoseEngine
from ..contracts import (
    PoseFrameResult,
    LandmarkPoint,
    ProcessingStatus,
    PoseStatus,
    ReasonCode,
)


class PoseEngineError(Exception):
    def __init__(self, reason_code: ReasonCode, message: str):
        super().__init__(f"[{reason_code.value}] {message}")
        self.reason_code = reason_code
        self.message = message


class MediaPipeTasksPoseEngine(PoseEngine):
    """MediaPipe Tasks PoseLandmarker 官方视频推理适配器"""

    def __init__(
        self,
        model_path: str = "models/pose_landmarker_full.task",
        expected_sha256: Optional[str] = None,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ):
        self.model_path = Path(model_path)
        self.expected_sha256 = expected_sha256
        self.min_detection_confidence = min_detection_confidence
        self.min_tracking_confidence = min_tracking_confidence
        self.landmarker = None
        self.last_timestamp_ms: Optional[int] = None

    def _verify_model_asset(self) -> None:
        if not self.model_path.exists():
            raise PoseEngineError(
                ReasonCode.MODEL_ASSET_MISSING,
                f"MediaPipe Tasks 模型资产未找到: {self.model_path}"
            )

        if self.expected_sha256:
            h = hashlib.sha256()
            with open(self.model_path, "rb") as f:
                while chunk := f.read(65536):
                    h.update(chunk)
            actual_sha256 = h.hexdigest()
            if actual_sha256.lower() != self.expected_sha256.lower():
                raise PoseEngineError(
                    ReasonCode.MODEL_HASH_MISMATCH,
                    f"模型文件哈希不匹配: 期望 {self.expected_sha256}, 实际 {actual_sha256}"
                )

    def initialize(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._verify_model_asset()

        try:
            import mediapipe as mp
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision

            base_options = python.BaseOptions(model_asset_path=str(self.model_path.resolve()))
            options = vision.PoseLandmarkerOptions(
                base_options=base_options,
                running_mode=vision.RunningMode.VIDEO,
                num_poses=1,
                min_pose_detection_confidence=self.min_detection_confidence,
                min_tracking_confidence=self.min_tracking_confidence,
                output_segmentation_masks=False,
            )
            self.landmarker = vision.PoseLandmarker.create_from_options(options)
            self.last_timestamp_ms = None
        except Exception as e:
            raise PoseEngineError(
                ReasonCode.ENGINE_INIT_FAILED,
                f"MediaPipe Tasks 引擎初始化失败: {e}"
            )

    def infer_frame(self, rgb_image: np.ndarray, timestamp_us: int) -> PoseFrameResult:
        if self.landmarker is None:
            raise PoseEngineError(
                ReasonCode.ENGINE_INIT_FAILED,
                "引擎尚未初始化，请先调用 initialize()"
            )

        try:
            import mediapipe as mp

            # MediaPipe Tasks detect_for_video 要求以毫秒为单位且严格递增
            timestamp_ms = int(timestamp_us // 1000)
            if self.last_timestamp_ms is not None and timestamp_ms <= self.last_timestamp_ms:
                # 若微秒量化到毫秒后发生重合，平滑补偿 +1ms 保持单调递增
                timestamp_ms = self.last_timestamp_ms + 1
            self.last_timestamp_ms = timestamp_ms

            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_image)
            result = self.landmarker.detect_for_video(mp_image, timestamp_ms)

            # 转换姿态结果为中立 DTO
            if not result.pose_landmarks or len(result.pose_landmarks) == 0:
                return PoseFrameResult(
                    processing_status=ProcessingStatus.OK,
                    pose_status=PoseStatus.NO_POSE,
                    landmarks_2d=[],
                )

            # 单人提取
            raw_landmarks = result.pose_landmarks[0]
            if len(raw_landmarks) != 33:
                return PoseFrameResult(
                    processing_status=ProcessingStatus.INVALID_MODEL_OUTPUT,
                    pose_status=PoseStatus.INVALID_MODEL_OUTPUT,
                    landmarks_2d=[],
                    engine_diagnostic=f"关键点数量异常 (期望33, 实际{len(raw_landmarks)})",
                )

            landmarks_2d = []
            for lm in raw_landmarks:
                landmarks_2d.append(
                    LandmarkPoint(
                        x=float(lm.x),
                        y=float(lm.y),
                        z=float(lm.z) if hasattr(lm, "z") else 0.0,
                        visibility=float(lm.visibility) if getattr(lm, "visibility", None) is not None else None,
                        presence=float(lm.presence) if getattr(lm, "presence", None) is not None else None,
                    )
                )

            landmarks_world = None
            if result.pose_world_landmarks and len(result.pose_world_landmarks) > 0:
                landmarks_world = []
                for wlm in result.pose_world_landmarks[0]:
                    landmarks_world.append(
                        LandmarkPoint(
                            x=float(wlm.x),
                            y=float(wlm.y),
                            z=float(wlm.z) if hasattr(wlm, "z") else 0.0,
                            visibility=float(wlm.visibility) if getattr(wlm, "visibility", None) is not None else None,
                            presence=float(wlm.presence) if getattr(wlm, "presence", None) is not None else None,
                        )
                    )

            return PoseFrameResult(
                processing_status=ProcessingStatus.OK,
                pose_status=PoseStatus.POSE_DETECTED,
                landmarks_2d=landmarks_2d,
                landmarks_world=landmarks_world,
            )

        except Exception as e:
            return PoseFrameResult(
                processing_status=ProcessingStatus.INFERENCE_FAILED,
                pose_status=PoseStatus.INVALID_MODEL_OUTPUT,
                landmarks_2d=[],
                engine_diagnostic=str(e),
            )

    def close(self) -> None:
        if self.landmarker is not None:
            try:
                self.landmarker.close()
            except Exception:
                pass
            self.landmarker = None
