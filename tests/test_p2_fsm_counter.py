# -*- coding: utf-8 -*-
"""
P2 状态机与可靠计数器对抗性与边界测试
测试场景:
1. 标准深蹲动作生命周期与原子计数 +1;
2. 半程深蹲 (未达深度) 夭折流转与防误加计数;
3. 临界滞后迟滞防抖 (Schmitt Trigger 抗震荡);
4. 快速连蹲切分 (精确计数 3);
5. 物理不可行超快抽搐动作拦截 (Duration Gate);
6. 最低点停留容忍与超时复位;
7. 突发连续丢帧容错降级与站立自愈.
"""

import pytest
from p2_temporal.contracts import (
    FsmState,
    RepetitionEvent,
    TemporalReasonCode,
)
from p2_temporal.fsm.state_machine import SquatPhaseFSM
from p2_temporal.counter.rep_counter import RepetitionCounter


def simulate_squat_cycle(
    fsm: SquatPhaseFSM,
    counter: RepetitionCounter,
    min_knee: float = 85.0,
    fps: float = 30.0,
    pause_bottom_frames: int = 10,
    start_frame_idx: int = 0,
):
    """辅助函数: 模拟一段完整的下蹲-起立时序曲线"""
    dt_us = int(1e6 / fps)
    current_frame = start_frame_idx
    current_time_us = start_frame_idx * dt_us

    # 1. 站立准备 (170度, 10帧)
    for _ in range(10):
        state, event, reasons = fsm.step(170.0, 0.0, True, current_frame, current_time_us)
        counter.update(state, event, 170.0, 5.0, current_frame, current_time_us, reasons)
        current_frame += 1
        current_time_us += dt_us

    # 2. 下蹲阶段 (从 170度平滑下降至 min_knee, 20帧)
    angles_desc = [170.0 - (170.0 - min_knee) * (i / 20.0) for i in range(1, 21)]
    for angle in angles_desc:
        state, event, reasons = fsm.step(angle, -10.0, True, current_frame, current_time_us)
        counter.update(state, event, angle, 20.0, current_frame, current_time_us, reasons)
        current_frame += 1
        current_time_us += dt_us

    # 3. 最低点停顿
    for _ in range(pause_bottom_frames):
        state, event, reasons = fsm.step(min_knee, 0.0, True, current_frame, current_time_us)
        counter.update(state, event, min_knee, 25.0, current_frame, current_time_us, reasons)
        current_frame += 1
        current_time_us += dt_us

    # 4. 起身阶段 (从 min_knee 平滑上升至 170度, 20帧)
    angles_asc = [min_knee + (170.0 - min_knee) * (i / 20.0) for i in range(1, 21)]
    for angle in angles_asc:
        state, event, reasons = fsm.step(angle, 10.0, True, current_frame, current_time_us)
        counter.update(state, event, angle, 15.0, current_frame, current_time_us, reasons)
        current_frame += 1
        current_time_us += dt_us

    # 5. 再次站立锁死 (170度, 10帧)
    for _ in range(10):
        state, event, reasons = fsm.step(170.0, 0.0, True, current_frame, current_time_us)
        counter.update(state, event, 170.0, 5.0, current_frame, current_time_us, reasons)
        current_frame += 1
        current_time_us += dt_us

    return current_frame, current_time_us


def test_standard_squat_cycle_success():
    """测试标准深蹲：状态按序流转，产生 COMPLETED 事件，计数增加 1"""
    fsm = SquatPhaseFSM()
    counter = RepetitionCounter(min_rep_duration_s=0.6)

    simulate_squat_cycle(fsm, counter, min_knee=85.0)

    assert counter.cumulative_rep_count == 1
    manifest = counter.get_manifest()
    assert manifest["total_completed_reps"] == 1
    assert len(manifest["repetitions"]) == 1

    rep = manifest["repetitions"][0]
    assert rep["is_valid"] is True
    assert rep["status"] == "COMPLETED"
    assert rep["min_knee_angle"] <= 85.0
    assert rep["duration_ms"] > 600.0


def test_half_squat_aborted_no_count():
    """测试半程深蹲（浅蹲：最低仅蹲到 125度，未达 100度阈值），计数绝不增加，且标记 ABORTED"""
    fsm = SquatPhaseFSM()
    counter = RepetitionCounter()

    simulate_squat_cycle(fsm, counter, min_knee=125.0)

    # 深度不足，计数器严禁增加！
    assert counter.cumulative_rep_count == 0
    manifest = counter.get_manifest()
    assert manifest["total_completed_reps"] == 0
    assert manifest["aborted_reps_count"] == 1
    assert manifest["repetitions"][0]["status"] == "ABORTED"
    assert TemporalReasonCode.ABORTED_INCOMPLETE_DEPTH.value in manifest["repetitions"][0]["reason_codes"]


def test_schmitt_trigger_hysteresis_anti_chattering():
    """测试施密特滞后带：在阈值 140 附近高频微小晃动 (138-142 度)，状态机不发生频繁跳变"""
    fsm = SquatPhaseFSM(desc_enter_thresh=140.0, desc_exit_thresh=160.0, debounce_frames=2)

    # 初始站立
    state, _, _ = fsm.step(170.0, 0.0, True, 0, 0)
    assert state == FsmState.STANDING

    # 屈膝进入 138 度持续 3 帧 -> 进入 DESCENDING
    fsm.step(138.0, -1.0, True, 1, 33333)
    fsm.step(138.0, -1.0, True, 2, 66666)
    state, _, _ = fsm.step(138.0, -1.0, True, 3, 100000)
    assert state == FsmState.DESCENDING

    # 在 142度 晃动（未触及退出线 160度）
    for i in range(4, 15):
        jitter_angle = 141.0 if i % 2 == 0 else 143.0
        state, _, _ = fsm.step(jitter_angle, 0.0, True, i, i * 33333)
        # 必须维持 DESCENDING，不发生震荡！
        assert state == FsmState.DESCENDING


def test_rapid_consecutive_squats():
    """测试快速连续深蹲：连续执行 3 次深蹲，最终计数精确等于 3"""
    fsm = SquatPhaseFSM()
    counter = RepetitionCounter()

    end_frame = 0
    for _ in range(3):
        end_frame, _ = simulate_squat_cycle(fsm, counter, min_knee=80.0, start_frame_idx=end_frame)

    assert counter.cumulative_rep_count == 3
    manifest = counter.get_manifest()
    assert manifest["total_completed_reps"] == 3
    assert len(manifest["repetitions"]) == 3


def test_fast_jitter_duration_gate_discarded():
    """测试物理不可行超快抽搐动作（全过程耗时 0.2s < 0.6s），被时长防火墙阻断作废"""
    fsm = SquatPhaseFSM(debounce_frames=1)
    counter = RepetitionCounter(min_rep_duration_s=0.6)

    # 在极短时间 (200ms) 内完成下蹲和起立
    dt_us = 20000  # 20ms 一帧，共 10 帧 = 200ms
    frames = [170.0, 130.0, 95.0, 95.0, 120.0, 168.0, 170.0]
    for i, a in enumerate(frames):
        state, event, reasons = fsm.step(a, 0.0, True, i, i * dt_us)
        counter.update(state, event, a, 10.0, i, i * dt_us, reasons)

    # 计数被阻断
    assert counter.cumulative_rep_count == 0
    manifest = counter.get_manifest()
    assert manifest["aborted_reps_count"] == 1
    assert TemporalReasonCode.DISCARDED_TOO_FAST.value in manifest["repetitions"][0]["reason_codes"]


def test_dropout_inertia_and_degraded_recovery():
    """测试连续丢帧容错：丢 2 帧保持状态，丢 5 帧降级至 DEGRADED，恢复站立自愈"""
    fsm = SquatPhaseFSM()

    # 1. 处于下蹲中
    fsm.step(130.0, -5.0, True, 0, 0)
    fsm.step(130.0, -5.0, True, 1, 33333)
    state, _, _ = fsm.step(130.0, -5.0, True, 2, 66666)
    assert state == FsmState.DESCENDING

    # 2. 连续 2 帧丢失关键点 (is_valid=False) -> 惯性保持在 DESCENDING
    s1, _, _ = fsm.step(180.0, 0.0, False, 3, 100000)
    s2, _, _ = fsm.step(180.0, 0.0, False, 4, 133333)
    assert s1 == FsmState.DESCENDING
    assert s2 == FsmState.DESCENDING

    # 3. 累计丢帧达到 4 帧 (> max_inertia_frames=3) -> 降级为 DEGRADED
    fsm.step(180.0, 0.0, False, 5, 166666)
    s4, event, reasons = fsm.step(180.0, 0.0, False, 6, 200000)
    assert s4 == FsmState.DEGRADED
    assert event == RepetitionEvent.REP_DISRUPTED

    # 4. 受试者重新在站立姿态被检测到 (170度) -> 自愈回到 STANDING
    s_rec, _, _ = fsm.step(170.0, 0.0, True, 7, 233333)
    assert s_rec == FsmState.STANDING
