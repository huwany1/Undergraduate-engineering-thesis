# -*- coding: utf-8 -*-
"""
独立视频推理工作器 (Inference Task Worker)
五大架构指标保障:
1. 高内聚 (High Cohesion): 将模型加载、逐帧视频提取、时序机推进与规则卡评估彻底封装为独立 Worker;
2. 高性能 (High Performance): 实施动态自适应分帧采样 (高帧率自适应步长 + 波谷关键区间密集保真);
3. 高可用 (High Availability): 内置超时看门狗 (Timeout Watchdog) 与取消信号, 具备异常隔离与资源强力释放.
"""

import cv2
import time
import json
import logging
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

from p1_pipeline.engine.tasks_adapter import MediaPipeTasksPoseEngine
from p1_pipeline.quality_gate import QualityGate
from p1_pipeline.contracts import OverlayStatus
from p2_temporal.runner import P2TemporalPipeline
from p2_temporal.analytics import MultiRepAnalyticsEngine
from p3_rules.engine import SquatAssessmentEngine
from p3_rules.contracts import RuleCardConfig, AssessmentStatus
from .contracts import UniversalFeedbackFormatter

logger = logging.getLogger("web_demo.worker")


class InferenceTaskWorker:
    """
    单任务视频推理工作器
    负责单个视频文件的生命周期执行：解码 -> 姿态估计 -> 运动学滤波与计数 -> 规则质检 -> 结果组装
    """

    def __init__(
        self,
        task_id: str,
        video_path: Path,
        original_filename: str,
        model_path: Path,
        screenshot_dir: Path,
        sidecar_dir: Path,
        summary_dir: Path,
        repo_root: Path,
        timeout_sec: float = 60.0,
    ):
        self.task_id = task_id
        self.video_path = Path(video_path)
        self.original_filename = original_filename
        self.model_path = Path(model_path)
        self.screenshot_dir = Path(screenshot_dir)
        self.sidecar_dir = Path(sidecar_dir)
        self.summary_dir = Path(summary_dir)
        self.repo_root = Path(repo_root)
        self.timeout_sec = timeout_sec

        self.cancel_event = threading.Event()
        self.is_running = False

    def cancel(self):
        """发送优雅取消信号"""
        self.cancel_event.set()

    def execute(
        self,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> Dict[str, Any]:
        """
        同步执行端到端视频分析流水线 (通常在后台线程池调用)
        :param progress_callback: 进度推进回调函数 (progress_int, stage_name)
        :return: 规范同构的 AssessmentReport 结果字典
        """
        self.is_running = True
        start_time = time.perf_counter()

        def report_progress(pct: int, msg: str):
            if progress_callback:
                try:
                    progress_callback(pct, msg)
                except Exception:
                    pass

        cap = None
        engine = None

        try:
            # -------------------------------------------------------------
            # Stage 1: 视频元数据探测与步长自适应规划 (10%)
            # -------------------------------------------------------------
            report_progress(10, "读取视频元数据并探测动作特征...")
            if not self.video_path.exists():
                raise FileNotFoundError(f"视频文件不存在: {self.video_path}")

            cap = cv2.VideoCapture(str(self.video_path))
            if not cap.isOpened():
                raise RuntimeError("OpenCV 无法解码该视频流，文件可能损坏或编码不受支持")

            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            if fps <= 0 or fps != fps:
                fps = 30.0
            if total_frames <= 0:
                total_frames = 150

            # 动态自适应分帧采样策略 (满足 3~5s 实时响应 SLA, 高帧率视频等效抽帧)
            base_stride = 1
            if fps >= 50.0:
                base_stride = 2
            elif total_frames > 350:
                base_stride = max(1, int(total_frames / 160))

            # -------------------------------------------------------------
            # Stage 2: 预热姿态引擎与算法组件 (25%)
            # -------------------------------------------------------------
            report_progress(25, "MediaPipe 逐帧骨骼关键点提取与滤波解算 (P1 & P2)...")

            engine = MediaPipeTasksPoseEngine(
                model_path=str(self.model_path),
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            engine.initialize()

            quality_gate = QualityGate()
            p2_pipeline = P2TemporalPipeline()

            frame_idx = 0
            sampled_count = 0
            total_to_process = max(1, (total_frames + base_stride - 1) // base_stride)
            telemetry: List[Dict[str, Any]] = []
            keyframes: List[Dict[str, Any]] = []

            min_knee_ever = 180.0
            best_trough_frame = None
            best_trough_idx = 0

            # -------------------------------------------------------------
            # Stage 3: 逐帧提取与状态机计算循环 (带超时看门狗熔断与下蹲波谷密集保真)
            # -------------------------------------------------------------
            in_squat_zone = False

            while True:
                # 3.1 超时看门狗与取消信号检查
                elapsed = time.perf_counter() - start_time
                if elapsed > self.timeout_sec:
                    raise TimeoutError(f"推理任务执行超时 (运行已达 {elapsed:.1f}s, 熔断上限 {self.timeout_sec}s)")
                if self.cancel_event.is_set():
                    raise RuntimeError("任务已被客户端主动取消")

                ret, frame = cap.read()
                if not ret:
                    break

                # 3.2 动态自适应步长：波谷减速区自适应密集采样, 直立阶段跳帧加速
                active_stride = 1 if in_squat_zone else base_stride
                if frame_idx % active_stride != 0:
                    frame_idx += 1
                    continue

                time_s = frame_idx / fps
                timeline_us = int(time_s * 1e6)

                # 3.3 MediaPipe 姿态推理
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pose_res = engine.infer_frame(rgb, timeline_us)

                # 3.4 质量门控与 P2 时序解算
                quality = quality_gate.evaluate(pose_res)
                is_valid = (quality.overlay_status == OverlayStatus.DRAWABLE) and (len(pose_res.landmarks_2d) == 33)
                side = quality.required_side.value if quality.required_side else "LEFT"

                p2_res = p2_pipeline.process_frame(
                    frame_index=frame_idx,
                    timeline_us=timeline_us,
                    landmarks_2d=pose_res.landmarks_2d,
                    side=side,
                    is_frame_valid=is_valid,
                )

                kine = p2_res.kinematics
                fsm_val = p2_res.fsm_state.value if hasattr(p2_res.fsm_state, "value") else str(p2_res.fsm_state)
                event_val = p2_res.event.value if hasattr(p2_res.event, "value") else str(p2_res.event)

                # 动态自适应判断是否处于下蹲关键区 (膝角弯曲 < 140° 或 FSM 非直立)
                if kine.is_valid and (kine.filtered_knee_angle < 140.0 or fsm_val in ("SQUATTING", "BOTTOM_HOLD", "RISING")):
                    in_squat_zone = True
                else:
                    in_squat_zone = False

                landmarks_data = []
                if pose_res.landmarks_2d:
                    landmarks_data = [
                        [round(p.x, 4), round(p.y, 4), round(p.visibility if p.visibility is not None else 1.0, 2)]
                        for p in pose_res.landmarks_2d
                    ]

                telemetry.append({
                    "frame_index": frame_idx,
                    "time_s": round(time_s, 3),
                    "knee_angle": round(kine.filtered_knee_angle, 1),
                    "raw_knee_angle": round(kine.raw_knee_angle, 1),
                    "torso_angle": round(kine.filtered_torso_angle, 1),
                    "raw_torso_angle": round(kine.raw_torso_angle, 1),
                    "fsm_state": fsm_val,
                    "event": event_val,
                    "is_valid": kine.is_valid,
                    "count": p2_res.cumulative_rep_count,
                    "landmarks": landmarks_data,
                })

                # 记录全局最低膝角候选
                if kine.is_valid and kine.filtered_knee_angle < min_knee_ever:
                    min_knee_ever = kine.filtered_knee_angle
                    best_trough_frame = frame.copy()
                    best_trough_idx = frame_idx

                # 捕获关键特征快照
                if event_val in ("INFLECTION_REACHED", "REP_COMPLETED"):
                    kf_filename = f"{self.task_id}_kf_{frame_idx}_{event_val}.png"
                    kf_path = self.screenshot_dir / kf_filename
                    cv2.imwrite(str(kf_path), frame)
                    desc = (
                        f"动作波谷极值 (膝角: {kine.filtered_knee_angle:.1f}°, 前倾: {kine.filtered_torso_angle:.1f}°)"
                        if event_val == "INFLECTION_REACHED"
                        else f"完成深蹲 #{p2_res.cumulative_rep_count}"
                    )
                    keyframes.append({
                        "event_type": event_val,
                        "frame_index": frame_idx,
                        "timeline_us": timeline_us,
                        "description": desc,
                        "image_url": f"/api/media/uploaded/screenshot/{kf_filename}",
                    })

                sampled_count += 1
                frame_idx += 1

                # 动态进度平滑推进 (25% ~ 75%)
                if sampled_count % 8 == 0:
                    pct = 25 + int(50 * (sampled_count / total_to_process))
                    report_progress(min(75, pct), "MediaPipe 逐帧骨骼关键点提取与滤波解算 (P1 & P2)...")

            # 兜底：若动作未触发标准事件但存在有效画面，捕获极值帧
            if not keyframes and best_trough_frame is not None:
                kf_filename = f"{self.task_id}_kf_{best_trough_idx}_trough.png"
                kf_path = self.screenshot_dir / kf_filename
                cv2.imwrite(str(kf_path), best_trough_frame)
                keyframes.append({
                    "event_type": "MIN_KNEE_TROUGH",
                    "frame_index": best_trough_idx,
                    "timeline_us": int((best_trough_idx / fps) * 1e6),
                    "description": f"实测下蹲最低点 (膝角: {min_knee_ever:.1f}°)",
                    "image_url": f"/api/media/uploaded/screenshot/{kf_filename}",
                })

            # -------------------------------------------------------------
            # Stage 4: P3 规则卡质检与反馈评估 (80%)
            # -------------------------------------------------------------
            report_progress(80, "执行 P3 规则卡质检与非医疗指导生成...")

            completed_reps = [r for r in p2_pipeline.counter.records if r.status == "COMPLETED" or r.is_valid]
            assessment_engine = SquatAssessmentEngine(config=RuleCardConfig())
            assessments = assessment_engine.evaluate_all(completed_reps)

            total_reps = len(completed_reps)
            passed_reps = sum(1 for a in assessments if a.overall_status == AssessmentStatus.ACCEPTABLE)

            valid_telemetry = [t for t in telemetry if t["is_valid"]]
            min_knee = min([t["knee_angle"] for t in valid_telemetry], default=min_knee_ever)
            max_torso = max([t["torso_angle"] for t in valid_telemetry], default=0.0)

            # 判定综合状态与主原因码
            all_reasons = []
            for a in assessments:
                for v in a.violations:
                    if v.reason_code not in all_reasons:
                        all_reasons.append(v.reason_code)

            if total_reps > 0:
                if passed_reps == total_reps:
                    overall_status = "ACCEPTABLE"
                    primary_reason = "NONE"
                else:
                    overall_status = "NEEDS_IMPROVEMENT"
                    first_defect = next((a for a in assessments if a.overall_status != AssessmentStatus.ACCEPTABLE), assessments[0])
                    primary_reason = first_defect.primary_reason_code.value if hasattr(first_defect.primary_reason_code, "value") else str(first_defect.primary_reason_code)
            else:
                valid_ratio = len(valid_telemetry) / max(1, len(telemetry))
                if valid_ratio < 0.4:
                    overall_status = "REJECTED"
                    primary_reason = "OUT_OF_FRAME"
                else:
                    overall_status = "NEEDS_IMPROVEMENT"
                    primary_reason = "INCOMPLETE_CYCLE"

            if not all_reasons and primary_reason != "NONE":
                all_reasons.append(primary_reason)

            # 使用通用反馈格式化器 (彻底解耦 case_id)
            summary_feedback = UniversalFeedbackFormatter.format(
                status=overall_status,
                primary_reason=primary_reason,
                min_knee=min_knee,
                max_torso=max_torso,
                total_reps=total_reps,
                all_reasons=all_reasons,
            )

            # -------------------------------------------------------------
            # Stage 5: 结果持久化与组装同构报告 (95%)
            # -------------------------------------------------------------
            report_progress(95, "持久化遥测 Sidecar 并渲染报告...")

            sidecar_path = self.sidecar_dir / f"{self.task_id}_frames.jsonl"
            with open(sidecar_path, "w", encoding="utf-8") as sf:
                for row in telemetry:
                    sf.write(json.dumps(row, ensure_ascii=False) + "\n")

            total_elapsed_ms = (time.perf_counter() - start_time) * 1000

            ext_bio_summary = {
                "min_valgus_ratio": min([r.extended_metrics.get("min_valgus_ratio") for r in completed_reps if r.extended_metrics and r.extended_metrics.get("min_valgus_ratio") is not None], default=None),
                "max_heel_lift_deg": max([r.extended_metrics.get("max_heel_lift_deg", 0.0) for r in completed_reps if r.extended_metrics], default=0.0),
                "max_pelvic_tilt_deg": max([r.extended_metrics.get("max_pelvic_tilt_deg", 0.0) for r in completed_reps if r.extended_metrics], default=0.0),
                "max_bilateral_diff_deg": max([r.extended_metrics.get("max_bilateral_diff_deg") for r in completed_reps if r.extended_metrics and r.extended_metrics.get("max_bilateral_diff_deg") is not None], default=None),
            }

            multi_rep_summary = MultiRepAnalyticsEngine.analyze(completed_reps, assessments).to_dict()

            report_result = {
                "case_id": f"UPLOAD_{self.task_id}",
                "task_id": self.task_id,
                "case_name": f"自定义分析: {Path(self.original_filename).name}",
                "description": f"在线分析视频 (原帧率 {fps:.1f} FPS, 共解算 {len(telemetry)} 帧, 耗时 {total_elapsed_ms / 1000:.2f}s)",
                "expected_count": None,
                "expected_status": None,
                "expected_primary_reason": None,
                "actual_count": total_reps,
                "actual_status": overall_status,
                "actual_primary_reason": primary_reason,
                "actual_reason_codes": all_reasons,
                "measured_min_knee_angle": round(min_knee, 1),
                "measured_max_torso_angle": round(max_torso, 1),
                "extended_biomechanics": ext_bio_summary,
                "execution_time_ms": round(total_elapsed_ms, 1),
                "summary_feedback": summary_feedback,
                "has_video": True,
                "video_url": f"/api/media/uploaded/video/{self.video_path.name}",
                "telemetry": telemetry,
                "keyframes": keyframes,
                "assessments": [a.to_dict() for a in assessments],
                "repetitions": [r.to_dict() for r in completed_reps],
                "multi_rep_summary": multi_rep_summary,
            }

            summary_path = self.summary_dir / f"{self.task_id}_summary.json"
            with open(summary_path, "w", encoding="utf-8") as sum_f:
                json.dump(report_result, sum_f, indent=2, ensure_ascii=False)

            report_progress(100, "分析完成！专属报告与回放曲线已就绪。")
            return report_result

        finally:
            self.is_running = False
            if cap is not None:
                cap.release()
            if engine is not None:
                try:
                    engine.close()
                except Exception:
                    pass
