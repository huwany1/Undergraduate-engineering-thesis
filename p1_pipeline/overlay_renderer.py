# -*- coding: utf-8 -*-
"""
P1 二维骨架与状态叠加渲染器 (OverlayRenderer)
依据: P1_姿态视频链路_P0级详细实施方案.md (Section 06.3)
"""

from typing import List, Tuple, Optional
import cv2
import numpy as np

from .contracts import (
    FrameEnvelope,
    PoseFrameResult,
    FrameQuality,
    PoseStatus,
)


class OverlayRenderer:
    """在原始图像帧上绘制 2D 骨架与技术状态 HUD，严格禁止任何业务评价文案"""

    # 33 点拓扑连接表 (MediaPipe 标准骨架连接)
    SKELETON_CONNECTIONS: List[Tuple[int, int]] = [
        (0, 1), (1, 2), (2, 3), (3, 7),
        (0, 4), (4, 5), (5, 6), (6, 8),
        (9, 10),
        (11, 12), (11, 13), (13, 15), (15, 17), (15, 19), (15, 21), (17, 19),
        (12, 14), (14, 16), (16, 18), (16, 20), (16, 22), (18, 20),
        (11, 23), (12, 24), (23, 24),
        (23, 25), (24, 26), (25, 27), (26, 28),
        (27, 29), (28, 30), (29, 31), (30, 32),
        (27, 31), (28, 32)
    ]

    def __init__(
        self,
        joint_color_bgr: Tuple[int, int, int] = (0, 255, 0),    # 绿色
        bone_color_bgr: Tuple[int, int, int] = (255, 200, 0),   # 浅青蓝
        hud_text_color: Tuple[int, int, int] = (255, 255, 255), # 白色
        hud_bg_color: Tuple[int, int, int] = (30, 30, 30),      # 深灰
        point_radius: int = 4,
        line_thickness: int = 2,
    ):
        self.joint_color = joint_color_bgr
        self.bone_color = bone_color_bgr
        self.hud_text_color = hud_text_color
        self.hud_bg_color = hud_bg_color
        self.point_radius = point_radius
        self.line_thickness = line_thickness

    def render(
        self,
        envelope: FrameEnvelope,
        pose_result: PoseFrameResult,
        quality: FrameQuality
    ) -> np.ndarray:
        # 复制 BGR 底图
        canvas = envelope.decoded_bgr.copy()
        h, w = canvas.shape[:2]

        # 1. 骨架与关节绘制
        if pose_result.pose_status == PoseStatus.POSE_DETECTED and len(pose_result.landmarks_2d) == 33:
            landmarks = pose_result.landmarks_2d
            pixel_coords = []
            for lm in landmarks:
                px = int(round(lm.x * w))
                py = int(round(lm.y * h))
                pixel_coords.append((px, py))

            # 绘制允许的连线（两端点均通过门控）
            for start_idx, end_idx in self.SKELETON_CONNECTIONS:
                start_valid = quality.joint_validity.get(start_idx, {}).get("allowed_for_overlay", False)
                end_valid = quality.joint_validity.get(end_idx, {}).get("allowed_for_overlay", False)

                if start_valid and end_valid:
                    p1 = pixel_coords[start_idx]
                    p2 = pixel_coords[end_idx]
                    cv2.line(canvas, p1, p2, self.bone_color, self.line_thickness)

            # 绘制允许的点
            for idx, (px, py) in enumerate(pixel_coords):
                pt_valid = quality.joint_validity.get(idx, {}).get("allowed_for_overlay", False)
                if pt_valid:
                    cv2.circle(canvas, (px, py), self.point_radius, self.joint_color, -1)

        # 2. 技术状态 HUD 绘制（避开中间身体运动区域，置于左上角）
        hud_lines = [
            f"Frame: {envelope.frame_index} | Time: {envelope.timeline_us / 1e6:.2f}s",
            f"Pose: {pose_result.pose_status.value} | Overlay: {quality.overlay_status.value}",
            f"Side: {quality.required_side.value if quality.required_side else 'N/A'}",
        ]
        if quality.reason_codes:
            reasons_str = ",".join([rc.value for rc in quality.reason_codes[:2]])
            hud_lines.append(f"Reasons: {reasons_str}")

        # 绘制半透明背景条
        line_height = 20
        box_h = len(hud_lines) * line_height + 14
        box_w = min(360, w - 20)
        cv2.rectangle(canvas, (10, 10), (10 + box_w, 10 + box_h), self.hud_bg_color, -1)

        for i, text in enumerate(hud_lines):
            y_pos = 28 + (i * line_height)
            cv2.putText(
                canvas,
                text,
                (16, y_pos),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                self.hud_text_color,
                1,
                cv2.LINE_AA,
            )

        return canvas
