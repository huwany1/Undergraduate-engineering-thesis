# -*- coding: utf-8 -*-
"""
P1 契约、DTO 与质量门控单元测试
"""

import pytest
import numpy as np
from p1_pipeline.contracts import (
    LandmarkPoint,
    PoseFrameResult,
    FrameEnvelope,
    FrameQuality,
    ProcessingStatus,
    PoseStatus,
    OverlayStatus,
    Side,
    ReasonCode,
)
from p1_pipeline.quality_gate import QualityGate
from p1_pipeline.overlay_renderer import OverlayRenderer


def test_landmark_point_null_handling():
    """验证 visibility 与 presence 字段保留 None，不强制替换为 0"""
    pt = LandmarkPoint(x=0.5, y=0.5, z=0.0, visibility=None, presence=None)
    d = pt.to_dict()
    assert d["visibility"] is None
    assert d["presence"] is None
    assert d["x"] == 0.5


def test_pose_frame_result_neutral_dto():
    """验证 PoseFrameResult 序列化与中立性"""
    pts = [LandmarkPoint(x=0.1 * i, y=0.2 * i) for i in range(33)]
    res = PoseFrameResult(
        processing_status=ProcessingStatus.OK,
        pose_status=PoseStatus.POSE_DETECTED,
        landmarks_2d=pts,
    )
    d = res.to_dict()
    assert d["processing_status"] == "OK"
    assert d["pose_status"] == "POSE_DETECTED"
    assert len(d["landmarks_2d"]) == 33
    assert d["landmarks_world"] is None


def test_quality_gate_no_pose():
    """验证未检测到姿态时输出 POSE_ABSENT 及 NO_POSE 原因码"""
    qg = QualityGate()
    no_pose_res = PoseFrameResult(
        processing_status=ProcessingStatus.OK,
        pose_status=PoseStatus.NO_POSE,
        landmarks_2d=[],
    )
    q = qg.evaluate(no_pose_res)
    assert q.overlay_status == OverlayStatus.POSE_ABSENT
    assert ReasonCode.NO_POSE in q.reason_codes


def test_quality_gate_out_of_frame():
    """验证关键关节越界时输出 REQUIRED_JOINT_INVALID 与 REQUIRED_JOINT_OUT_OF_FRAME"""
    qg = QualityGate(calibration_window_frames=1)
    # 构造左侧膝盖(25)越界的 33 点姿态
    pts = []
    for i in range(33):
        x = 1.5 if i == 25 else 0.5
        y = 0.5
        pts.append(LandmarkPoint(x=x, y=y, visibility=0.9, presence=0.9))

    res = PoseFrameResult(
        processing_status=ProcessingStatus.OK,
        pose_status=PoseStatus.POSE_DETECTED,
        landmarks_2d=pts,
    )
    q = qg.evaluate(res)
    assert q.overlay_status == OverlayStatus.REQUIRED_JOINT_INVALID
    assert ReasonCode.REQUIRED_JOINT_OUT_OF_FRAME in q.reason_codes


def test_quality_gate_low_visibility():
    """验证关键关节低可见度时被抑制与记录"""
    qg = QualityGate(calibration_window_frames=1, visibility_threshold=0.6)
    qg.locked_side = Side.LEFT
    pts = []
    for i in range(33):
        # 髋关节(23)可见度 0.2
        vis = 0.2 if i == 23 else 0.9
        pts.append(LandmarkPoint(x=0.5, y=0.5, visibility=vis, presence=0.9))

    res = PoseFrameResult(
        processing_status=ProcessingStatus.OK,
        pose_status=PoseStatus.POSE_DETECTED,
        landmarks_2d=pts,
    )
    q = qg.evaluate(res)
    assert q.overlay_status == OverlayStatus.REQUIRED_JOINT_INVALID
    assert ReasonCode.REQUIRED_JOINT_LOW_VISIBILITY in q.reason_codes


def test_overlay_renderer_no_business_claims():
    """验证 2D 骨架渲染不包含动作评价或深蹲计数等业务违规文案"""
    renderer = OverlayRenderer()
    dummy_bgr = np.zeros((240, 320, 3), dtype=np.uint8)
    dummy_rgb = np.zeros((240, 320, 3), dtype=np.uint8)
    envelope = FrameEnvelope(
        run_id="run-test",
        frame_index=0,
        timeline_us=0,
        decoded_bgr=dummy_bgr,
        decoded_rgb=dummy_rgb,
        width=320,
        height=240,
    )
    pts = [LandmarkPoint(x=0.5, y=0.5, visibility=0.9, presence=0.9) for _ in range(33)]
    pose_res = PoseFrameResult(
        processing_status=ProcessingStatus.OK,
        pose_status=PoseStatus.POSE_DETECTED,
        landmarks_2d=pts,
    )
    qg = QualityGate(calibration_window_frames=1)
    quality = qg.evaluate(pose_res)

    rendered = renderer.render(envelope, pose_res, quality)
    assert rendered.shape == (240, 320, 3)
