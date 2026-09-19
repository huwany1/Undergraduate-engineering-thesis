# -*- coding: utf-8 -*-
"""
P2 时序闭环流水线调度执行器 (Temporal Pipeline Runner)
依据: P2_时序闭环_详细实施方案.md (Section 05 & 10)
职责:
1. 消费 P1 输出的中立 DTO 或 JSONL 证据流;
2. 调度运动学特征提取、1€ 滤波、有限状态机与可靠计数器;
3. 生成 P2 结构化 Sidecar 与 Repetitions 清单文件.
"""

import json
import os
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Iterator

from .contracts import (
    FsmState,
    RepetitionEvent,
    TemporalReasonCode,
    MotionKinematics,
    P2FrameResult,
)
from .kinematics.calculator import KinematicsCalculator
from .smoothing.one_euro_filter import OneEuroFilter
from .fsm.state_machine import SquatPhaseFSM
from .counter.rep_counter import RepetitionCounter


class P2TemporalPipeline:
    def __init__(
        self,
        knee_min_cutoff: float = 1.0,
        knee_beta: float = 0.005,
        torso_min_cutoff: float = 0.8,
        torso_beta: float = 0.003,
        fsm_params: Optional[Dict[str, Any]] = None,
        min_rep_duration_s: float = 0.6,
    ):
        self.kinematics_calc = KinematicsCalculator()
        self.knee_filter = OneEuroFilter(min_cutoff=knee_min_cutoff, beta=knee_beta)
        self.torso_filter = OneEuroFilter(min_cutoff=torso_min_cutoff, beta=torso_beta)

        fsm_kwargs = fsm_params or {}
        self.fsm = SquatPhaseFSM(**fsm_kwargs)
        self.counter = RepetitionCounter(min_rep_duration_s=min_rep_duration_s)

    def reset(self) -> None:
        """重置整条时序流水线的所有状态"""
        self.kinematics_calc.reset_baseline()
        self.knee_filter.reset()
        self.torso_filter.reset()
        self.fsm.reset()
        self.counter.reset()

    def process_frame(
        self,
        frame_index: int,
        timeline_us: int,
        landmarks_2d: List[Any],
        side: str = "LEFT",
        is_frame_valid: bool = True,
    ) -> P2FrameResult:
        """
        逐帧处理核心逻辑 (O(1) 增量因果计算)
        :param frame_index: 帧序列号
        :param timeline_us: 时间戳 (微秒)
        :param landmarks_2d: 33 个 2D 关键点
        :param side: 'LEFT' 或 'RIGHT'
        :param is_frame_valid: 来自 P1 QualityGate 的可用性门控判定
        :return: P2FrameResult DTO
        """
        timestamp_s = timeline_us / 1e6

        # 1. 提取原始几何运动学特征
        raw_knee, raw_torso, hip_y_norm, geom_valid = self.kinematics_calc.extract_features(
            landmarks_2d, side=side
        )

        overall_valid = is_frame_valid and geom_valid

        # 2. 自适应滤波 (即使当前帧无效，也传入上一值保持平滑)
        if overall_valid:
            filt_knee, knee_vel = self.knee_filter.filter_step(raw_knee, timestamp_s)
            filt_torso, torso_vel = self.torso_filter.filter_step(raw_torso, timestamp_s)
        else:
            # 短时丢帧时，滤波器复用上一平滑值并让速度归零
            filt_knee = self.knee_filter.prev_x if self.knee_filter.prev_x is not None else raw_knee
            knee_vel = 0.0
            filt_torso = self.torso_filter.prev_x if self.torso_filter.prev_x is not None else raw_torso
            torso_vel = 0.0

        extended_bio = self.kinematics_calc.extract_extended_biomechanics(
            landmarks_2d, side=side, current_torso_angle=raw_torso
        )

        kinematics = MotionKinematics(
            raw_knee_angle=raw_knee,
            filtered_knee_angle=filt_knee,
            knee_angular_velocity=knee_vel,
            raw_torso_angle=raw_torso,
            filtered_torso_angle=filt_torso,
            torso_angular_velocity=torso_vel,
            hip_y_norm=hip_y_norm,
            is_valid=overall_valid,
            knee_valgus_ratio=extended_bio.get("valgus_ratio"),
            heel_lift_deg=extended_bio.get("heel_lift_deg"),
            pelvic_tilt_deg=extended_bio.get("pelvic_tilt_deg"),
            bilateral_knee_diff=extended_bio.get("bilateral_knee_diff"),
        )

        # 3. 驱动有限状态机流转
        new_state, event, reasons = self.fsm.step(
            knee_angle=filt_knee,
            knee_velocity=knee_vel,
            is_valid=overall_valid,
            frame_index=frame_index,
            timeline_us=timeline_us,
        )

        # 4. 更新动作生命周期与可靠计数器
        cumulative_reps = self.counter.update(
            fsm_state=new_state,
            event=event,
            knee_angle=filt_knee,
            torso_angle=filt_torso,
            frame_index=frame_index,
            timeline_us=timeline_us,
            reason_codes=reasons,
            extended_kinematics=extended_bio,
        )

        active_id = self.counter.active_rep_id if self.counter.in_progress else None

        return P2FrameResult(
            frame_index=frame_index,
            timeline_us=timeline_us,
            fsm_state=new_state,
            cumulative_rep_count=cumulative_reps,
            event=event,
            kinematics=kinematics,
            active_rep_id=active_id,
            reason_codes=reasons,
        )

    def run_from_p1_sidecar(
        self,
        p1_sidecar_path: str,
        output_dir: str,
        required_side: str = "LEFT",
    ) -> Dict[str, Any]:
        """
        消费现有的 P1 Sidecar JSONL 文件，执行全量时序分析并输出归档产物
        """
        self.reset()
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        p2_sidecar_path = out_dir / "p2_sidecar.jsonl"
        rep_manifest_path = out_dir / "repetitions_manifest.json"
        summary_path = out_dir / "p2_summary.json"

        start_perf = time.perf_counter()
        total_frames = 0

        with open(p1_sidecar_path, "r", encoding="utf-8") as in_f, open(
            p2_sidecar_path, "w", encoding="utf-8"
        ) as out_f:
            for line in in_f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                total_frames += 1

                frame_idx = record.get("frame_index", total_frames - 1)
                timeline_us = record.get("timeline_us", frame_idx * 33333)

                pose_result = record.get("pose_result") or record.get("pose", {})
                landmarks = pose_result.get("landmarks_2d", [])

                quality = record.get("quality", {})
                overlay_status = quality.get("overlay_status", "DRAWABLE")
                is_valid = (overlay_status == "DRAWABLE") and (len(landmarks) == 33)

                side = quality.get("required_side") or required_side

                frame_res = self.process_frame(
                    frame_index=frame_idx,
                    timeline_us=timeline_us,
                    landmarks_2d=landmarks,
                    side=side,
                    is_frame_valid=is_valid,
                )

                out_f.write(json.dumps(frame_res.to_dict()) + "\n")

        elapsed_s = time.perf_counter() - start_perf
        fps = total_frames / max(elapsed_s, 1e-6)

        manifest = self.counter.get_manifest()
        with open(rep_manifest_path, "w", encoding="utf-8") as rf:
            json.dump(manifest, rf, indent=2, ensure_ascii=False)

        summary = {
            "total_frames_processed": total_frames,
            "elapsed_seconds": round(elapsed_s, 4),
            "throughput_fps": round(fps, 1),
            "cumulative_reps": manifest["total_completed_reps"],
            "attempted_reps": manifest["total_attempted_reps"],
            "aborted_reps": manifest["aborted_reps_count"],
        }
        with open(summary_path, "w", encoding="utf-8") as sf:
            json.dump(summary, sf, indent=2, ensure_ascii=False)

        return summary
