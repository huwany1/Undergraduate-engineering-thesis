# -*- coding: utf-8 -*-
"""
P4 多模态可视化叠加渲染器 (Multimodal Overlay Renderer)
依据: P4_验证包_详细实施方案.md (Section 07.2)
"""

import math
from typing import List, Tuple, Optional, Dict, Any
import cv2
import numpy as np

from p1_pipeline.contracts import LandmarkPoint
from p2_temporal.contracts import FsmState
from p3_rules.contracts import RepetitionAssessment, AssessmentStatus
from .contracts import TestCaseId, KeyframeEventType


class P4OverlayRenderer:
    """高保真离线多模态证据渲染器"""

    SKELETON_CONNECTIONS = [
        (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
        (11, 23), (12, 24), (23, 24),
        (23, 25), (24, 26), (25, 27), (26, 28),
        (27, 29), (28, 30), (29, 31), (30, 32), (27, 31), (28, 32),
    ]

    def __init__(self, width: int = 1280, height: int = 720):
        self.width = width
        self.height = height
        self.sidebar_width = 340
        self.main_width = width - self.sidebar_width

    def render_frame(
        self,
        frame_bgr: Optional[np.ndarray],
        landmarks: List[LandmarkPoint],
        frame_index: int,
        timeline_us: int,
        fsm_state: FsmState,
        cumulative_count: int,
        knee_angle: float,
        torso_angle: float,
        is_valid: bool,
        case_id: TestCaseId,
        assessment: Optional[RepetitionAssessment] = None,
        event_badge: Optional[KeyframeEventType] = None,
    ) -> np.ndarray:
        """
        合成完整的高保真视频帧与证据边栏
        """
        # 1. 准备主画布
        if frame_bgr is not None and frame_bgr.shape[0] == self.height and frame_bgr.shape[1] == self.width:
            canvas = frame_bgr.copy()
        else:
            # 创建现代科技深灰底色画布 (BGR: 22, 22, 28)
            canvas = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            canvas[:] = (28, 22, 22)

        # 2. 绘制人体骨架 (在主展示区)
        if is_valid and len(landmarks) == 33:
            pixel_coords = []
            for lm in landmarks:
                # 映射到主展示区 [0, main_width]
                px = int(round(lm.x * self.main_width))
                py = int(round(lm.y * self.height))
                pixel_coords.append((px, py))

            # 骨骼连线
            for s_idx, e_idx in self.SKELETON_CONNECTIONS:
                if s_idx < len(pixel_coords) and e_idx < len(pixel_coords):
                    p1 = pixel_coords[s_idx]
                    p2 = pixel_coords[e_idx]
                    if 0 <= p1[0] < self.main_width and 0 <= p2[0] < self.main_width:
                        cv2.line(canvas, p1, p2, (230, 200, 60), 2, cv2.LINE_AA)

            # 关键节点高亮
            for idx in [11, 12, 23, 24, 25, 26, 27, 28]:
                if idx < len(pixel_coords):
                    p = pixel_coords[idx]
                    if 0 <= p[0] < self.main_width:
                        cv2.circle(canvas, p, 5, (0, 230, 118), -1, cv2.LINE_AA)
                        cv2.circle(canvas, p, 7, (255, 255, 255), 1, cv2.LINE_AA)

            # 绘制膝关节夹角标注弧
            knee_pt = pixel_coords[25]
            hip_pt = pixel_coords[23]
            ankle_pt = pixel_coords[27]
            if 0 <= knee_pt[0] < self.main_width:
                cv2.putText(
                    canvas,
                    f"Knee: {knee_angle:.1f} deg",
                    (knee_pt[0] + 15, knee_pt[1] - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 255, 255),
                    2,
                    cv2.LINE_AA,
                )

            # 绘制躯干前倾夹角线
            if 0 <= hip_pt[0] < self.main_width:
                # 垂直参考虚线
                vert_top = (hip_pt[0], max(0, hip_pt[1] - 120))
                cv2.line(canvas, hip_pt, vert_top, (180, 180, 180), 1, cv2.LINE_AA)
                cv2.putText(
                    canvas,
                    f"Torso: {torso_angle:.1f} deg",
                    (hip_pt[0] - 120, hip_pt[1] - 50),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (255, 180, 0),
                    2,
                    cv2.LINE_AA,
                )
        elif not is_valid:
            # 无效帧警示标志
            cv2.putText(
                canvas,
                "[OUT OF FRAME / LOW QUALITY]",
                (self.main_width // 4, self.height // 2),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (0, 0, 255),
                2,
                cv2.LINE_AA,
            )

        # 3. 绘制右侧独立数据与证据面板 (Sidebar)
        sidebar_x = self.main_width
        # 填充侧边栏底色 (BGR: 35, 30, 30)
        canvas[:, sidebar_x:] = (38, 30, 30)
        cv2.line(canvas, (sidebar_x, 0), (sidebar_x, self.height), (70, 70, 70), 2)

        # 侧边栏文字排版
        def put_side_text(text: str, y: int, color=(255, 255, 255), scale=0.55, thick=1):
            cv2.putText(
                canvas, text, (sidebar_x + 15, y),
                cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA
            )

        # 顶部标题与元数据
        put_side_text("[P4] VALIDATION SUITE", 35, color=(0, 230, 118), scale=0.65, thick=2)
        put_side_text(f"Case: {case_id.value}", 65, color=(200, 200, 200), scale=0.45)
        put_side_text(f"Frame: {frame_index:04d} | {(timeline_us / 1000.0):.1f} ms", 90, color=(180, 180, 180), scale=0.45)

        cv2.line(canvas, (sidebar_x + 10, 105), (self.width - 10, 105), (60, 60, 60), 1)

        # 时序状态监测
        put_side_text("TEMPORAL MONITOR", 130, color=(255, 200, 0), scale=0.55, thick=2)
        put_side_text(f"Phase: {fsm_state.value}", 160, color=(255, 255, 255), scale=0.55, thick=2)
        put_side_text(f"Squat Count: {cumulative_count}", 190, color=(0, 255, 255), scale=0.6, thick=2)
        put_side_text(f"Knee Angle:  {knee_angle:.1f} deg", 220, color=(220, 220, 220))
        put_side_text("  (Baseline <= 100.0 deg)", 240, color=(140, 140, 140), scale=0.4)
        put_side_text(f"Torso Lean:  {torso_angle:.1f} deg", 265, color=(220, 220, 220))
        put_side_text("  (Baseline <= 35.0 deg)", 285, color=(140, 140, 140), scale=0.4)

        cv2.line(canvas, (sidebar_x + 10, 305), (self.width - 10, 305), (60, 60, 60), 1)

        # 规则评估证据面板
        put_side_text("RULE ASSESSMENT", 330, color=(255, 200, 0), scale=0.55, thick=2)
        if assessment is not None:
            # 状态彩色标签
            status_color = (0, 230, 118) if assessment.overall_status == AssessmentStatus.ACCEPTABLE else \
                           (0, 165, 255) if assessment.overall_status == AssessmentStatus.NEEDS_IMPROVEMENT else (0, 0, 255)
            put_side_text(f"Status: {assessment.overall_status.value}", 360, color=status_color, scale=0.6, thick=2)
            put_side_text(f"Reason: {assessment.primary_reason_code}", 390, color=(255, 255, 255), scale=0.5)

            y_offset = 425
            for v in assessment.violations[:2]:
                put_side_text(f"* {v.reason_code}", y_offset, color=(0, 165, 255), scale=0.45)
                if v.evidence:
                    ev_text = f"  Meas: {v.evidence.measured_value:.1f} | Delta: {v.evidence.delta_value:+.1f}"
                    put_side_text(ev_text, y_offset + 20, color=(180, 180, 180), scale=0.4)
                y_offset += 45
        else:
            put_side_text("Status: IN PROGRESS", 360, color=(180, 180, 180), scale=0.5)
            put_side_text("Awaiting Repetition Completion...", 390, color=(140, 140, 140), scale=0.4)

        # 事件标记徽章 (若为关键事件帧)
        if event_badge:
            cv2.rectangle(canvas, (sidebar_x + 15, 540), (self.width - 15, 580), (0, 100, 200), -1)
            cv2.putText(
                canvas, f"KEYFRAME: {event_badge.value}",
                (sidebar_x + 25, 565),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA
            )

        # 底部免责声明
        cv2.line(canvas, (sidebar_x + 10, 620), (self.width - 10, 620), (60, 60, 60), 1)
        put_side_text("NON-MEDICAL DISCLAIMER", 645, color=(150, 150, 150), scale=0.4, thick=1)
        put_side_text("For fitness coaching only.", 665, color=(120, 120, 120), scale=0.38)
        put_side_text("No medical diagnostic claim.", 685, color=(120, 120, 120), scale=0.38)

        return canvas
