# -*- coding: utf-8 -*-
"""
在线视频分析调度器与任务生命周期管理器 (Online Video Analysis Engine)
职责:
1. 接收前端上传的 MP4 视频流并实施安全校验 (大小、格式);
2. 异步调度 MediaPipe Tasks (P1) -> 1€ 滤波 & FSM (P2) -> 规则卡评估 (P3) 端到端推理;
3. 毫秒级提取动作波谷与达标特征关键帧快照;
4. 维护内存任务注册表 (TaskRegistry)，支持平滑百分比与阶段推进轮询;
5. 针对 Web 快速响应实施自适应采样优化，确保 3~5 秒内产出专属时序报告与回放曲线。
"""

import os
import re
import cv2
import time
import uuid
import json
import logging
import threading
from enum import Enum
from pathlib import Path
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Optional, Tuple

from p1_pipeline.engine.tasks_adapter import MediaPipeTasksPoseEngine
from p1_pipeline.quality_gate import QualityGate
from p1_pipeline.contracts import OverlayStatus
from p2_temporal.runner import P2TemporalPipeline
from p2_temporal.contracts import RepetitionRecord
from p3_rules.engine import SquatAssessmentEngine
from p3_rules.contracts import RuleCardConfig, AssessmentStatus

logger = logging.getLogger("web_demo.analyzer")


class AnalysisTaskStatus(str, Enum):
    """分析任务状态机"""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class AnalysisTask:
    """分析任务数据载体"""
    task_id: str
    status: AnalysisTaskStatus
    progress: int  # 0 ~ 100
    stage_name: str
    created_at: float
    video_filename: str
    video_rel_path: str = ""
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


def parse_upload_payload(
    body_bytes: bytes,
    content_type: str,
    query_filename: Optional[str] = None,
) -> Tuple[str, bytes]:
    """
    轻量、安全、零外部依赖的上传数据解析器。
    兼容 multipart/form-data 与原始流式 binary video/mp4。
    """
    if not body_bytes:
        raise ValueError("上传内容为空")

    # 1. 尝试按 multipart/form-data 解析
    if "multipart/form-data" in content_type:
        boundary = None
        for part in content_type.split(";"):
            part = part.strip()
            if part.startswith("boundary="):
                boundary = part.split("boundary=")[1].strip('"').strip("'").encode("utf-8")
                break
        if not boundary:
            raise ValueError("无效的 multipart/form-data: 缺少 boundary 标识")

        delimiter = b"--" + boundary
        parts = body_bytes.split(delimiter)
        for p in parts:
            if not p or p.startswith(b"--"):
                continue
            if b"\r\n\r\n" in p:
                header_data, file_content = p.split(b"\r\n\r\n", 1)
                # 剔除尾部回车换行符
                if file_content.endswith(b"\r\n"):
                    file_content = file_content[:-2]
                header_str = header_data.decode("utf-8", errors="replace")
                if 'filename="' in header_str:
                    fn_match = re.search(r'filename="([^"]+)"', header_str)
                    filename = fn_match.group(1) if fn_match else "uploaded_video.mp4"
                    return filename, file_content

        raise ValueError("未在 multipart 表单中解析出有效文件数据")

    # 2. 原始流式分块直传 (application/octet-stream 或 video/mp4)
    filename = query_filename or "uploaded_video.mp4"
    return filename, body_bytes


class OnlineAnalysisManager:
    """在线视频分析调度与任务生命周期管理器 (线程安全)"""

    MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
    MAX_RETAINED_TASKS = 50                 # 任务注册表最大留存

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = Path(repo_root) if repo_root else Path(__file__).resolve().parent.parent
        self.work_root = self.repo_root / "reports" / "uploaded_demo"
        self.upload_dir = self.work_root / "uploads"
        self.screenshot_dir = self.work_root / "screenshots"
        self.sidecar_dir = self.work_root / "sidecars"
        self.summary_dir = self.work_root / "summaries"
        self.model_path = self.repo_root / "models" / "pose_landmarker_full.task"

        # 创建目录结构
        for d in (self.upload_dir, self.screenshot_dir, self.sidecar_dir, self.summary_dir):
            d.mkdir(parents=True, exist_ok=True)

        self._tasks: Dict[str, AnalysisTask] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="OnlineAnalysisWorker")

    def submit_video(
        self,
        file_bytes: bytes,
        original_filename: str,
    ) -> str:
        """提交视频进行异步在线分析，返回任务 ID"""
        # 1. 严格文件大小门控
        if len(file_bytes) > self.MAX_FILE_SIZE_BYTES:
            raise ValueError(f"文件大小超出限制 (当前 {len(file_bytes) / 1024 / 1024:.1f}MB, 上限 50MB)")

        # 2. 文件格式与基本魔数校验 (检测 MP4 ftyp 签名)
        is_mp4 = (
            original_filename.lower().endswith(".mp4") or
            (len(file_bytes) > 12 and b"ftyp" in file_bytes[:32])
        )
        if not is_mp4:
            raise ValueError("仅支持 MP4 格式视频文件")

        task_id = f"up_{uuid.uuid4().hex[:10]}"
        clean_ext = ".mp4"
        clean_name = f"{task_id}_{Path(original_filename).stem[:20]}{clean_ext}"
        saved_video_path = self.upload_dir / clean_name

        with open(saved_video_path, "wb") as f:
            f.write(file_bytes)

        task = AnalysisTask(
            task_id=task_id,
            status=AnalysisTaskStatus.PENDING,
            progress=0,
            stage_name="视频上传成功，正在排队启动流水线...",
            created_at=time.time(),
            video_filename=original_filename,
            video_rel_path=str(saved_video_path.relative_to(self.repo_root)).replace("\\", "/"),
        )

        with self._lock:
            # 清理历史旧任务
            if len(self._tasks) >= self.MAX_RETAINED_TASKS:
                oldest_id = min(self._tasks.keys(), key=lambda k: self._tasks[k].created_at)
                del self._tasks[oldest_id]
            self._tasks[task_id] = task

        # 提交后台工作线程
        self._executor.submit(self._run_pipeline, task_id, saved_video_path, original_filename)
        return task_id

    def get_task(self, task_id: str) -> Optional[AnalysisTask]:
        """获取指定任务当前状态"""
        with self._lock:
            return self._tasks.get(task_id)

    def list_completed_sessions(self) -> List[Dict[str, Any]]:
        """获取全部已完成的用户上传分析记录概览"""
        with self._lock:
            completed = []
            for t in self._tasks.values():
                if t.status == AnalysisTaskStatus.COMPLETED and t.result:
                    completed.append({
                        "case_id": t.result.get("case_id", f"UPLOAD_{t.task_id}"),
                        "task_id": t.task_id,
                        "case_name": t.result.get("case_name", t.video_filename),
                        "description": t.result.get("description", ""),
                        "actual_count": t.result.get("actual_count", 0),
                        "actual_status": t.result.get("actual_status", "UNKNOWN"),
                        "actual_primary_reason": t.result.get("actual_primary_reason", "NONE"),
                        "has_video": True,
                        "video_url": t.result.get("video_url"),
                        "created_at": t.created_at,
                    })
            # 按时间倒序
            completed.sort(key=lambda x: x["created_at"], reverse=True)
            return completed

    def _run_pipeline(self, task_id: str, video_path: Path, original_filename: str) -> None:
        """在后台线程执行端到端 P1 -> P2 -> P3 在线视频分析流水线"""
        task = self.get_task(task_id)
        if not task:
            return

        start_time = time.perf_counter()

        try:
            # Stage 1: 初始化与元数据探测 (10%)
            task.status = AnalysisTaskStatus.PROCESSING
            task.progress = 10
            task.stage_name = "读取视频元数据并探测动作特征..."

            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                raise RuntimeError("OpenCV 无法解码该视频流，文件可能已损坏或编码不受支持")

            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            if fps <= 0 or fps != fps:
                fps = 30.0
            if total_frames <= 0:
                total_frames = 150  # 容错估计

            # 自适应步长控制 (确保 3~5s SLA)
            # 深蹲动作频率通常为 0.3~0.5Hz，15~20 FPS 足以高保真还原波谷与角度极值
            stride = 1
            if fps > 25:
                stride = 2
            if total_frames > 300:
                stride = max(stride, int(total_frames / 150))

            # Stage 2: 预热姿态引擎与算法组件 (25%)
            task.progress = 25
            task.stage_name = "MediaPipe 逐帧骨骼关键点提取与滤波解算 (P1 & P2)..."

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
            total_to_process = max(1, (total_frames + stride - 1) // stride)
            telemetry: List[Dict[str, Any]] = []
            keyframes: List[Dict[str, Any]] = []

            # 记录波谷候选帧，确保无完整动作时亦有特征快照
            min_knee_ever = 180.0
            best_trough_frame = None
            best_trough_idx = 0

            # 逐帧循环处理
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_idx % stride != 0:
                    frame_idx += 1
                    continue

                time_s = frame_idx / fps
                timeline_us = int(time_s * 1e6)

                # MediaPipe 需要 RGB 格式
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pose_res = engine.infer_frame(rgb, timeline_us)

                # 质量门控判定
                quality = quality_gate.evaluate(pose_res)
                is_valid = (quality.overlay_status == OverlayStatus.DRAWABLE) and (len(pose_res.landmarks_2d) == 33)
                side = quality.required_side.value if quality.required_side else "LEFT"

                # P2 运动学与状态机
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

                # 捕获关键特征帧
                if event_val in ("INFLECTION_REACHED", "REP_COMPLETED"):
                    kf_filename = f"{task_id}_kf_{frame_idx}_{event_val}.png"
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

                # 进度动态递增 (25% ~ 75%)
                if sampled_count % 8 == 0:
                    pct = 25 + int(50 * (sampled_count / total_to_process))
                    task.progress = min(75, pct)

            cap.release()

            # 兜底：若动作未触发标准事件但存在有效画面，捕获极值帧
            if not keyframes and best_trough_frame is not None:
                kf_filename = f"{task_id}_kf_{best_trough_idx}_trough.png"
                kf_path = self.screenshot_dir / kf_filename
                cv2.imwrite(str(kf_path), best_trough_frame)
                keyframes.append({
                    "event_type": "MIN_KNEE_TROUGH",
                    "frame_index": best_trough_idx,
                    "timeline_us": int((best_trough_idx / fps) * 1e6),
                    "description": f"实测下蹲最低点 (膝角: {min_knee_ever:.1f}°)",
                    "image_url": f"/api/media/uploaded/screenshot/{kf_filename}",
                })

            # Stage 3: P3 规则卡质检与反馈评估 (80%)
            task.progress = 80
            task.stage_name = "执行 P3 规则卡质检与非医疗指导生成..."

            completed_reps = [r for r in p2_pipeline.counter.records if r.status == "COMPLETED" or r.is_valid]
            assessment_engine = SquatAssessmentEngine(config=RuleCardConfig())
            assessments = assessment_engine.evaluate_all(completed_reps)

            total_reps = len(completed_reps)
            passed_reps = sum(1 for a in assessments if a.overall_status == AssessmentStatus.ACCEPTABLE)

            valid_telemetry = [t for t in telemetry if t["is_valid"]]
            min_knee = min([t["knee_angle"] for t in valid_telemetry], default=min_knee_ever)
            max_torso = max([t["torso_angle"] for t in valid_telemetry], default=0.0)

            # 判定综合动作状态与生成建议文案
            if total_reps > 0:
                if passed_reps == total_reps:
                    overall_status = "ACCEPTABLE"
                    primary_reason = "NONE"
                    summary_feedback = (
                        f"动作规范度良好！成功识别并完成 {total_reps} 次达标深蹲。"
                        f"实测膝关节最小屈曲角达到 {min_knee:.1f}°（及格标准 ≤ 105.0°），"
                        f"躯干最大前倾角保持在 {max_torso:.1f}°（安全基准 ≤ 45.0°），动作节奏控制平稳。"
                    )
                else:
                    overall_status = "NEEDS_IMPROVEMENT"
                    first_defect = next((a for a in assessments if a.overall_status != AssessmentStatus.ACCEPTABLE), assessments[0])
                    primary_reason = first_defect.primary_reason_code.value if hasattr(first_defect.primary_reason_code, "value") else str(first_defect.primary_reason_code)
                    summary_feedback = (
                        f"动作要点待改进：共尝试 {total_reps} 次深蹲，其中 {passed_reps} 次达标。"
                        f"实测波谷膝角 {min_knee:.1f}°，最大前倾角 {max_torso:.1f}°。"
                        f"指导建议：{first_defect.summary_feedback}"
                    )
            else:
                # 未完成完整闭环动作
                valid_ratio = len(valid_telemetry) / max(1, len(telemetry))
                if valid_ratio < 0.4:
                    overall_status = "REJECTED"
                    primary_reason = "OUT_OF_FRAME"
                    summary_feedback = "前置质检门控一票否决：检测到受试者移出画幅或关键特征点严重遮挡，系统克制地拒绝输出动作次数，请调整机位确保全身入镜。"
                else:
                    overall_status = "NEEDS_IMPROVEMENT"
                    primary_reason = "INCOMPLETE_CYCLE"
                    summary_feedback = (
                        f"未检测到完整闭环的深蹲动作（实测最小膝角 {min_knee:.1f}°）。"
                        "请在训练时保持核心稳定，下蹲至大腿接近水平再平稳站起恢复直立。"
                    )

            # Stage 4: 结果持久化与组装 (95%)
            task.progress = 95
            task.stage_name = "持久化遥测 Sidecar 并渲染报告..."

            # 导出 Sidecar
            sidecar_path = self.sidecar_dir / f"{task_id}_frames.jsonl"
            with open(sidecar_path, "w", encoding="utf-8") as sf:
                for row in telemetry:
                    sf.write(json.dumps(row, ensure_ascii=False) + "\n")

            total_elapsed_ms = (time.perf_counter() - start_time) * 1000

            all_reasons = []
            for a in assessments:
                for v in a.violations:
                    if v.reason_code not in all_reasons:
                        all_reasons.append(v.reason_code)
            if not all_reasons and primary_reason != "NONE":
                all_reasons.append(primary_reason)

            ext_bio_summary = {
                "min_valgus_ratio": min([r.extended_metrics.get("min_valgus_ratio") for r in completed_reps if r.extended_metrics and r.extended_metrics.get("min_valgus_ratio") is not None], default=None),
                "max_heel_lift_deg": max([r.extended_metrics.get("max_heel_lift_deg", 0.0) for r in completed_reps if r.extended_metrics], default=0.0),
                "max_pelvic_tilt_deg": max([r.extended_metrics.get("max_pelvic_tilt_deg", 0.0) for r in completed_reps if r.extended_metrics], default=0.0),
                "max_bilateral_diff_deg": max([r.extended_metrics.get("max_bilateral_diff_deg") for r in completed_reps if r.extended_metrics and r.extended_metrics.get("max_bilateral_diff_deg") is not None], default=None),
            }

            # 组装与现有 Web 看板完全同构的报告结果
            report_result = {
                "case_id": f"UPLOAD_{task_id}",
                "task_id": task_id,
                "case_name": f"自定义分析: {Path(original_filename).name}",
                "description": f"在线分析视频 (原帧率 {fps:.1f} FPS, 共解算 {len(telemetry)} 帧, 耗时 {total_elapsed_ms / 1000:.2f}s)",
                "expected_count": None,
                "expected_status": None,
                "expected_primary_reason": None,
                "actual_count": total_reps,
                "actual_status": overall_status,
                "actual_primary_reason": primary_reason,
                "actual_reason_codes": all_reasons if all_reasons else [primary_reason],
                "measured_min_knee_angle": round(min_knee, 1),
                "measured_max_torso_angle": round(max_torso, 1),
                "extended_biomechanics": ext_bio_summary,
                "execution_time_ms": round(total_elapsed_ms, 1),
                "summary_feedback": summary_feedback,
                "has_video": True,
                "video_url": f"/api/media/uploaded/video/{video_path.name}",
                "telemetry": telemetry,
                "keyframes": keyframes,
                "assessments": [a.to_dict() for a in assessments],
            }

            # 写出总结 JSON
            summary_path = self.summary_dir / f"{task_id}_summary.json"
            with open(summary_path, "w", encoding="utf-8") as sum_f:
                json.dump(report_result, sum_f, indent=2, ensure_ascii=False)

            # Stage 5: 最终完成 (100%)
            task.result = report_result
            task.progress = 100
            task.status = AnalysisTaskStatus.COMPLETED
            task.stage_name = "分析完成！专属报告与回放曲线已就绪。"
            logger.info(f"Task {task_id} completed successfully in {total_elapsed_ms:.1f}ms")

        except Exception as e:
            logger.exception(f"Task {task_id} failed with error: {e}")
            task.status = AnalysisTaskStatus.FAILED
            task.error = str(e)
            task.stage_name = f"处理失败: {str(e)}"
