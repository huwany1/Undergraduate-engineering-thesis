# -*- coding: utf-8 -*-
"""
P4 自动化测试套件：确定性回放与跨次回放一致性验证测试
"""

import pytest
from p4_validation.contracts import TestCaseId
from p4_validation.golden_assets import SyntheticStreamGenerator
from p4_validation.replayer import DeterministicReplayer


def test_synthetic_stream_monotonicity():
    stream = SyntheticStreamGenerator.generate_case_stream(TestCaseId.TC_01_PERFECT_SQUAT)
    assert len(stream) > 40

    prev_time = -1
    for frame_idx, timeline_us, landmarks, is_valid in stream:
        assert timeline_us > prev_time
        prev_time = timeline_us
        assert len(landmarks) == 33
        assert is_valid is True


def test_replay_determinism_across_multiple_runs():
    replayer = DeterministicReplayer()
    stream = SyntheticStreamGenerator.generate_case_stream(TestCaseId.TC_01_PERFECT_SQUAT)

    # 运行第 1 次
    trace1 = replayer.replay_stream(TestCaseId.TC_01_PERFECT_SQUAT, stream)
    # 运行第 2 次
    trace2 = replayer.replay_stream(TestCaseId.TC_01_PERFECT_SQUAT, stream)

    assert trace1.final_count == trace2.final_count == 1
    assert trace1.total_frames == trace2.total_frames
    assert pytest.approx(trace1.min_knee_angle, abs=1e-5) == trace2.min_knee_angle
    assert pytest.approx(trace1.max_torso_angle, abs=1e-5) == trace2.max_torso_angle

    assert len(trace1.assessments) == len(trace2.assessments)
    ass1 = trace1.assessments[0]
    ass2 = trace2.assessments[0]
    assert ass1.overall_status == ass2.overall_status
    assert ass1.primary_reason_code == ass2.primary_reason_code


def test_replayer_reset_between_different_cases():
    replayer = DeterministicReplayer()

    # 先跑 TC_01
    stream1 = SyntheticStreamGenerator.generate_case_stream(TestCaseId.TC_01_PERFECT_SQUAT)
    trace1 = replayer.replay_stream(TestCaseId.TC_01_PERFECT_SQUAT, stream1)
    assert trace1.final_count == 1

    # 再跑 TC_05 (出框拒绝，期望 0 计)
    stream5 = SyntheticStreamGenerator.generate_case_stream(TestCaseId.TC_05_OUT_OF_FRAME)
    trace5 = replayer.replay_stream(TestCaseId.TC_05_OUT_OF_FRAME, stream5)

    # 确保 TC_01 的计数不会泄漏到 TC_05 中
    assert trace5.final_count == 0
    assert trace5.assessments[0].overall_status.value == "NOT_EVALUATED"
