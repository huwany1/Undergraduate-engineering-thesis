# -*- coding: utf-8 -*-
"""
施密特双滞后有限状态机 (Squat Phase FSM)
依据: P2_时序闭环_详细实施方案.md (Section 08)
特性:
1. 双滞后死区消除临界阈值震荡 (Chattering/Ping-Pong);
2. 状态驻留防抖 (Debounce);
3. 半程深蹲 (Half-squat) 夭折流转，防止死锁与误加计数;
4. 动作阶段停留超时熔断与恢复.
"""

from typing import Tuple, List, Optional
from ..contracts import FsmState, RepetitionEvent, TemporalReasonCode


class SquatPhaseFSM:
    def __init__(
        self,
        desc_enter_thresh: float = 140.0,
        desc_exit_thresh: float = 160.0,
        bottom_enter_thresh: float = 100.0,
        bottom_exit_thresh: float = 115.0,
        standing_enter_thresh: float = 165.0,
        debounce_frames: int = 2,
        max_phase_duration_s: float = 15.0,
    ):
        self.desc_enter_thresh = float(desc_enter_thresh)
        self.desc_exit_thresh = float(desc_exit_thresh)
        self.bottom_enter_thresh = float(bottom_enter_thresh)
        self.bottom_exit_thresh = float(bottom_exit_thresh)
        self.standing_enter_thresh = float(standing_enter_thresh)
        self.debounce_frames = int(debounce_frames)
        self.max_phase_duration_s = float(max_phase_duration_s)

        # 内部状态追踪
        self.state: FsmState = FsmState.STANDING
        self.candidate_state: Optional[FsmState] = None
        self.candidate_frames: int = 0

        self.phase_start_frame: int = 0
        self.phase_start_timeline_us: int = 0
        self.bottom_reached: bool = False

        # 丢帧连续计数
        self.invalid_frames_count: int = 0
        self.max_inertia_frames: int = 3

    def reset(self) -> None:
        """重置状态机到初始站立状态"""
        self.state = FsmState.STANDING
        self.candidate_state = None
        self.candidate_frames = 0
        self.phase_start_frame = 0
        self.phase_start_timeline_us = 0
        self.bottom_reached = False
        self.invalid_frames_count = 0

    def step(
        self,
        knee_angle: float,
        knee_velocity: float,
        is_valid: bool,
        frame_index: int,
        timeline_us: int,
    ) -> Tuple[FsmState, RepetitionEvent, List[TemporalReasonCode]]:
        """
        状态机单步流转
        :return: (current_state, event, reason_codes)
        """
        reasons: List[TemporalReasonCode] = []
        event = RepetitionEvent.NONE

        # 1. 关键点有效性与短时丢帧惯性保持 / 降级流转
        if not is_valid:
            self.invalid_frames_count += 1
            if self.invalid_frames_count > self.max_inertia_frames:
                # 超过惯性保持容忍窗口，强制降级
                prev_state = self.state
                self.state = FsmState.DEGRADED
                reasons.append(TemporalReasonCode.OCCLUSION_DEGRADED)
                if prev_state in (FsmState.DESCENDING, FsmState.BOTTOM, FsmState.ASCENDING):
                    event = RepetitionEvent.REP_DISRUPTED
                return self.state, event, reasons
            else:
                # 处于短时丢帧惯性容忍期，维持当前状态，不推进状态机候选
                return self.state, RepetitionEvent.NONE, reasons

        # 恢复有效，清零丢帧计数
        self.invalid_frames_count = 0

        # 从 DEGRADED 状态中恢复（必须回到接近直立站姿才允许退出 DEGRADED）
        if self.state == FsmState.DEGRADED:
            if knee_angle >= self.desc_exit_thresh:
                self.state = FsmState.STANDING
                self.candidate_state = None
                self.candidate_frames = 0
                self.bottom_reached = False
                reasons.append(TemporalReasonCode.NORMAL)
                return self.state, RepetitionEvent.PHASE_ENTER, reasons
            return self.state, RepetitionEvent.NONE, reasons

        # 2. 超时熔断保护检查 (单个动作持续超过 15 秒)
        phase_duration_s = (timeline_us - self.phase_start_timeline_us) / 1e6
        if self.state != FsmState.STANDING and phase_duration_s > self.max_phase_duration_s:
            self.state = FsmState.STANDING
            self.bottom_reached = False
            self.candidate_state = None
            self.candidate_frames = 0
            reasons.append(TemporalReasonCode.DISCARDED_TIMEOUT)
            return self.state, RepetitionEvent.REP_ABORTED, reasons

        # 3. 施密特双滞后状态判定目标候选 (Target Candidate)
        target_state = self.state

        if self.state == FsmState.STANDING:
            # 站立 -> 屈膝下蹲
            if knee_angle < self.desc_enter_thresh:
                target_state = FsmState.DESCENDING

        elif self.state == FsmState.DESCENDING:
            # 持续下蹲 -> 到达最低点
            if knee_angle <= self.bottom_enter_thresh:
                target_state = FsmState.BOTTOM
            # 半程放弃 -> 回到站立 (夭折路径)
            elif knee_angle > self.desc_exit_thresh:
                target_state = FsmState.STANDING

        elif self.state == FsmState.BOTTOM:
            self.bottom_reached = True
            # 最低点 -> 起身回弹
            if knee_angle > self.bottom_exit_thresh and knee_velocity >= -2.0:
                target_state = FsmState.ASCENDING

        elif self.state == FsmState.ASCENDING:
            # 起身 -> 回到站立锁死 (动作完成点)
            if knee_angle >= self.standing_enter_thresh:
                target_state = FsmState.STANDING
            # 起身中途再次下挫 (犹豫倒车)
            elif knee_angle < self.bottom_enter_thresh + 10.0 and knee_velocity < -5.0:
                target_state = FsmState.BOTTOM

        # 4. 防抖驻留逻辑 (Debounce Filter)
        if target_state != self.state:
            if self.candidate_state == target_state:
                self.candidate_frames += 1
            else:
                self.candidate_state = target_state
                self.candidate_frames = 1

            if self.candidate_frames >= self.debounce_frames:
                # 确认发生状态跳变！
                old_state = self.state
                new_state = self.candidate_state
                self.state = new_state
                self.candidate_state = None
                self.candidate_frames = 0
                self.phase_start_frame = frame_index
                self.phase_start_timeline_us = timeline_us

                # 判定跳变产生的业务事件
                if old_state == FsmState.ASCENDING and new_state == FsmState.STANDING:
                    # 正常完整完成！
                    if self.bottom_reached:
                        event = RepetitionEvent.REP_COMPLETED
                        reasons.append(TemporalReasonCode.NORMAL)
                    else:
                        event = RepetitionEvent.REP_ABORTED
                        reasons.append(TemporalReasonCode.ABORTED_INCOMPLETE_DEPTH)
                    self.bottom_reached = False

                elif old_state == FsmState.DESCENDING and new_state == FsmState.STANDING:
                    # 半程深蹲直接回升站立，触发夭折
                    event = RepetitionEvent.REP_ABORTED
                    reasons.append(TemporalReasonCode.ABORTED_INCOMPLETE_DEPTH)
                    self.bottom_reached = False

                else:
                    event = RepetitionEvent.PHASE_ENTER
        else:
            # 维持当前状态，清空候选
            self.candidate_state = None
            self.candidate_frames = 0

        return self.state, event, reasons
