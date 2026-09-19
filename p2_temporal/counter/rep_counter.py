# -*- coding: utf-8 -*-
"""
深蹲动作生命周期与可靠计数器 (Repetition Lifecycle Counter)
依据: P2_时序闭环_详细实施方案.md (Section 09)
特性:
1. 边沿触发单调原子自增;
2. 全生命周期切片跟踪 (start, bottom, end, min_knee_angle, max_torso_angle);
3. 最小/最大持续时间防火墙 (防止物理不可行的抽搐假动作误计数);
4. 异常夭折动作完整归档审计.
"""

from typing import List, Optional, Dict, Any
from ..contracts import (
    FsmState,
    RepetitionEvent,
    RepetitionRecord,
    TemporalReasonCode,
)


class RepetitionCounter:
    def __init__(self, min_rep_duration_s: float = 0.6):
        self.min_rep_duration_s = float(min_rep_duration_s)
        self.cumulative_rep_count: int = 0

        # 当前活跃深蹲切片暂存
        self.active_rep_id: int = 1
        self.in_progress: bool = False
        self.start_frame: int = 0
        self.start_timeline_us: int = 0
        self.bottom_frame: int = 0
        self.bottom_timeline_us: int = 0
        self.min_knee_angle: float = 180.0
        self.max_torso_lean_angle: float = 0.0

        # 扩展伤病隐患运动学特征极值暂存
        self.min_valgus_ratio: Optional[float] = None
        self.max_heel_lift_deg: float = 0.0
        self.max_pelvic_tilt_deg: float = 0.0
        self.max_bilateral_diff_deg: float = 0.0

        # 归档记录
        self.records: List[RepetitionRecord] = []

    def reset(self) -> None:
        """重置计数器所有状态"""
        self.cumulative_rep_count = 0
        self.active_rep_id = 1
        self.in_progress = False
        self.start_frame = 0
        self.start_timeline_us = 0
        self.bottom_frame = 0
        self.bottom_timeline_us = 0
        self.min_knee_angle = 180.0
        self.max_torso_lean_angle = 0.0
        self.min_valgus_ratio = None
        self.max_heel_lift_deg = 0.0
        self.max_pelvic_tilt_deg = 0.0
        self.max_bilateral_diff_deg = 0.0
        self.records.clear()

    def update(
        self,
        fsm_state: FsmState,
        event: RepetitionEvent,
        knee_angle: float,
        torso_angle: float,
        frame_index: int,
        timeline_us: int,
        reason_codes: Optional[List[TemporalReasonCode]] = None,
        extended_kinematics: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        根据当前帧状态机事件更新动作切片与计数器
        :return: 当前累计有效完成次数
        """
        reason_str_list = [r.value for r in (reason_codes or [])]

        # 1. 动作开始捕获: 从 STANDING 进入 DESCENDING
        if fsm_state == FsmState.DESCENDING and not self.in_progress:
            self.in_progress = True
            self.start_frame = frame_index
            self.start_timeline_us = timeline_us
            self.bottom_frame = frame_index
            self.bottom_timeline_us = timeline_us
            self.min_knee_angle = knee_angle
            self.max_torso_lean_angle = torso_angle
            self.min_valgus_ratio = None
            self.max_heel_lift_deg = 0.0
            self.max_pelvic_tilt_deg = 0.0
            self.max_bilateral_diff_deg = 0.0

        # 2. 动作进行中，持续统计特征极值
        if self.in_progress:
            if knee_angle < self.min_knee_angle:
                self.min_knee_angle = knee_angle
                self.bottom_frame = frame_index
                self.bottom_timeline_us = timeline_us

            if torso_angle > self.max_torso_lean_angle:
                self.max_torso_lean_angle = torso_angle

            if extended_kinematics:
                vr = extended_kinematics.get("valgus_ratio")
                if vr is not None:
                    self.min_valgus_ratio = min(self.min_valgus_ratio, vr) if self.min_valgus_ratio is not None else vr

                hl = extended_kinematics.get("heel_lift_deg")
                if hl is not None and hl > self.max_heel_lift_deg:
                    self.max_heel_lift_deg = hl

                pt = extended_kinematics.get("pelvic_tilt_deg")
                if pt is not None and pt > self.max_pelvic_tilt_deg:
                    self.max_pelvic_tilt_deg = pt

                bd = extended_kinematics.get("bilateral_knee_diff")
                if bd is not None and bd > self.max_bilateral_diff_deg:
                    self.max_bilateral_diff_deg = bd

        ext_metrics = {
            "min_valgus_ratio": round(self.min_valgus_ratio, 3) if self.min_valgus_ratio is not None else None,
            "max_heel_lift_deg": round(self.max_heel_lift_deg, 2),
            "max_pelvic_tilt_deg": round(self.max_pelvic_tilt_deg, 2),
            "max_bilateral_diff_deg": round(self.max_bilateral_diff_deg, 2) if self.max_bilateral_diff_deg > 0.0 else None,
        }

        # 3. 处理完成事件 (REP_COMPLETED)
        if event == RepetitionEvent.REP_COMPLETED:
            if self.in_progress:
                duration_ms = (timeline_us - self.start_timeline_us) / 1000.0
                desc_duration_ms = (self.bottom_timeline_us - self.start_timeline_us) / 1000.0
                asc_duration_ms = (timeline_us - self.bottom_timeline_us) / 1000.0

                # 时长防火墙拦截
                if duration_ms < (self.min_rep_duration_s * 1000.0):
                    # 动作过快，判定为抽搐噪点
                    record = RepetitionRecord(
                        rep_id=self.active_rep_id,
                        is_valid=False,
                        status="ABORTED",
                        start_frame=self.start_frame,
                        bottom_frame=self.bottom_frame,
                        end_frame=frame_index,
                        start_timeline_us=self.start_timeline_us,
                        bottom_timeline_us=self.bottom_timeline_us,
                        end_timeline_us=timeline_us,
                        duration_ms=duration_ms,
                        descending_duration_ms=desc_duration_ms,
                        ascending_duration_ms=asc_duration_ms,
                        min_knee_angle=self.min_knee_angle,
                        max_torso_lean_angle=self.max_torso_lean_angle,
                        reason_codes=[TemporalReasonCode.DISCARDED_TOO_FAST.value] + reason_str_list,
                        extended_metrics=ext_metrics,
                    )
                    self.records.append(record)
                else:
                    # 合法完成！原子累加
                    self.cumulative_rep_count += 1
                    record = RepetitionRecord(
                        rep_id=self.active_rep_id,
                        is_valid=True,
                        status="COMPLETED",
                        start_frame=self.start_frame,
                        bottom_frame=self.bottom_frame,
                        end_frame=frame_index,
                        start_timeline_us=self.start_timeline_us,
                        bottom_timeline_us=self.bottom_timeline_us,
                        end_timeline_us=timeline_us,
                        duration_ms=duration_ms,
                        descending_duration_ms=desc_duration_ms,
                        ascending_duration_ms=asc_duration_ms,
                        min_knee_angle=self.min_knee_angle,
                        max_torso_lean_angle=self.max_torso_lean_angle,
                        reason_codes=[TemporalReasonCode.NORMAL.value] + reason_str_list,
                        extended_metrics=ext_metrics,
                    )
                    self.records.append(record)
                    self.active_rep_id += 1

                # 清空当前动作切片
                self.in_progress = False

        # 4. 处理异常夭折 (REP_ABORTED 或 REP_DISRUPTED)
        elif event in (RepetitionEvent.REP_ABORTED, RepetitionEvent.REP_DISRUPTED):
            if self.in_progress:
                duration_ms = (timeline_us - self.start_timeline_us) / 1000.0
                desc_duration_ms = max(0.0, (self.bottom_timeline_us - self.start_timeline_us) / 1000.0)
                asc_duration_ms = max(0.0, (timeline_us - self.bottom_timeline_us) / 1000.0)

                record = RepetitionRecord(
                    rep_id=self.active_rep_id,
                    is_valid=False,
                    status="ABORTED" if event == RepetitionEvent.REP_ABORTED else "DISRUPTED",
                    start_frame=self.start_frame,
                    bottom_frame=self.bottom_frame,
                    end_frame=frame_index,
                    start_timeline_us=self.start_timeline_us,
                    bottom_timeline_us=self.bottom_timeline_us,
                    end_timeline_us=timeline_us,
                    duration_ms=duration_ms,
                    descending_duration_ms=desc_duration_ms,
                    ascending_duration_ms=asc_duration_ms,
                    min_knee_angle=self.min_knee_angle,
                    max_torso_lean_angle=self.max_torso_lean_angle,
                    reason_codes=reason_str_list,
                    extended_metrics=ext_metrics,
                )
                self.records.append(record)
                self.active_rep_id += 1
                self.in_progress = False

        return self.cumulative_rep_count

    def get_manifest(self) -> Dict[str, Any]:
        """导出全量动作切片清单与汇总报告"""
        valid_reps = [r for r in self.records if r.is_valid]
        return {
            "total_completed_reps": self.cumulative_rep_count,
            "total_attempted_reps": len(self.records),
            "valid_reps_count": len(valid_reps),
            "aborted_reps_count": len(self.records) - len(valid_reps),
            "repetitions": [r.to_dict() for r in self.records],
        }
