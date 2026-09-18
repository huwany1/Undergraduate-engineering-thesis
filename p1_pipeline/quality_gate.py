# -*- coding: utf-8 -*-
"""
P1 质量门控模块 (QualityGate)
依据: P1_姿态视频链路_P0级详细实施方案.md (Section 04.4 & 06)
"""

import math
from typing import List, Dict, Any, Optional
from .contracts import (
    PoseFrameResult,
    FrameQuality,
    OverlayStatus,
    Side,
    ReasonCode,
    PoseStatus,
)


class QualityGate:
    """仅针对 P1 姿态可用性与侧别锁定执行质量门控，绝不计算动作角度或质量评分"""

    def __init__(
        self,
        calibration_window_frames: int = 10,
        visibility_threshold: float = 0.5,
        presence_threshold: float = 0.5,
        allow_unknown_fields: bool = True,
    ):
        self.calibration_window_frames = calibration_window_frames
        self.visibility_threshold = visibility_threshold
        self.presence_threshold = presence_threshold
        self.allow_unknown_fields = allow_unknown_fields

        self.locked_side: Optional[Side] = None
        self.calibration_history: List[Dict[str, float]] = []
        self.processed_frames = 0

        # 核心关节索引定义
        self.key_joints = {
            Side.LEFT: {"shoulder": 11, "hip": 23, "knee": 25, "ankle": 27},
            Side.RIGHT: {"shoulder": 12, "hip": 24, "knee": 26, "ankle": 28},
        }

    def _evaluate_point(self, point, idx: int) -> Dict[str, Any]:
        """评估单个关键点的有限性、在框性及可见度"""
        is_finite = not (math.isnan(point.x) or math.isnan(point.y) or math.isinf(point.x) or math.isinf(point.y))
        in_frame = is_finite and (0.0 <= point.x <= 1.0) and (0.0 <= point.y <= 1.0)

        vis_ok = True
        if point.visibility is not None:
            vis_ok = (point.visibility >= self.visibility_threshold)
        elif not self.allow_unknown_fields:
            vis_ok = False

        pres_ok = True
        if point.presence is not None:
            pres_ok = (point.presence >= self.presence_threshold)
        elif not self.allow_unknown_fields:
            pres_ok = False

        allowed_for_overlay = is_finite and in_frame and vis_ok and pres_ok

        return {
            "index": idx,
            "finite": is_finite,
            "in_frame": in_frame,
            "visibility_ok": vis_ok,
            "presence_ok": pres_ok,
            "allowed_for_overlay": allowed_for_overlay,
        }

    def evaluate(self, pose_result: PoseFrameResult) -> FrameQuality:
        self.processed_frames += 1

        # 1. 无姿态处理
        if pose_result.pose_status != PoseStatus.POSE_DETECTED or len(pose_result.landmarks_2d) < 33:
            return FrameQuality(
                overlay_status=OverlayStatus.POSE_ABSENT,
                required_side=self.locked_side,
                required_joints=["shoulder", "hip", "knee", "ankle"],
                joint_validity={},
                reason_codes=[ReasonCode.NO_POSE],
            )

        landmarks = pose_result.landmarks_2d

        # 2. 逐点检查有效性
        joint_validity = {}
        for idx, pt in enumerate(landmarks):
            joint_validity[idx] = self._evaluate_point(pt, idx)

        # 3. 计算左右侧关键关节可见度均值
        left_scores = []
        for j_idx in self.key_joints[Side.LEFT].values():
            vis = landmarks[j_idx].visibility
            left_scores.append(vis if vis is not None else 0.8)
        left_mean = sum(left_scores) / len(left_scores)

        right_scores = []
        for j_idx in self.key_joints[Side.RIGHT].values():
            vis = landmarks[j_idx].visibility
            right_scores.append(vis if vis is not None else 0.8)
        right_mean = sum(right_scores) / len(right_scores)

        # 4. 侧别锁定逻辑（校准窗内确定，之后整段固定）
        if self.locked_side is None:
            self.calibration_history.append({"left": left_mean, "right": right_mean})
            if len(self.calibration_history) >= self.calibration_window_frames:
                avg_left = sum(h["left"] for h in self.calibration_history) / len(self.calibration_history)
                avg_right = sum(h["right"] for h in self.calibration_history) / len(self.calibration_history)
                if abs(avg_left - avg_right) < 0.05:
                    # 可见度几乎无差异，暂时倾向于更高者或标记模糊
                    self.locked_side = Side.LEFT if avg_left >= avg_right else Side.RIGHT
                else:
                    self.locked_side = Side.LEFT if avg_left > avg_right else Side.RIGHT
            else:
                # 校准窗内临时选取
                temp_side = Side.LEFT if left_mean >= right_mean else Side.RIGHT
                active_side = temp_side
        else:
            active_side = self.locked_side

        effective_side = self.locked_side or active_side

        # 5. 检查锁定侧的关键关节是否满足门控
        side_joints = self.key_joints[effective_side]
        reason_codes: List[ReasonCode] = []
        overlay_status = OverlayStatus.DRAWABLE

        # 侧别歧义或跳变检查
        if self.locked_side is not None:
            # 若对侧可见度明显持续高于锁定侧，报告可能侧别变化
            current_favored = Side.LEFT if left_mean > right_mean + 0.3 else (Side.RIGHT if right_mean > left_mean + 0.3 else None)
            if current_favored is not None and current_favored != self.locked_side:
                reason_codes.append(ReasonCode.POSE_SIDE_CHANGED)
                overlay_status = OverlayStatus.SIDE_CHANGED

        for j_name, j_idx in side_joints.items():
            jv = joint_validity[j_idx]
            if not jv["finite"]:
                reason_codes.append(ReasonCode.REQUIRED_JOINT_NONFINITE)
                overlay_status = OverlayStatus.REQUIRED_JOINT_INVALID
            elif not jv["in_frame"]:
                reason_codes.append(ReasonCode.REQUIRED_JOINT_OUT_OF_FRAME)
                overlay_status = OverlayStatus.REQUIRED_JOINT_INVALID
            elif not (jv["visibility_ok"] and jv["presence_ok"]):
                reason_codes.append(ReasonCode.REQUIRED_JOINT_LOW_VISIBILITY)
                overlay_status = OverlayStatus.REQUIRED_JOINT_INVALID

        # 去重保持顺序
        seen = set()
        unique_reason_codes = []
        for rc in reason_codes:
            if rc not in seen:
                seen.add(rc)
                unique_reason_codes.append(rc)

        return FrameQuality(
            overlay_status=overlay_status,
            required_side=effective_side,
            required_joints=list(side_joints.keys()),
            joint_validity=joint_validity,
            reason_codes=unique_reason_codes,
        )
