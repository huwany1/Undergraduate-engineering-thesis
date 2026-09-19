# -*- coding: utf-8 -*-
"""
实时视频流分析调度引擎与会话生命周期管理器 (Live Stream Session Engine)
依据: 维度一实时交互理想 Demo 水准技术规范
职责:
1. 管理单个客户端/摄像头的实时流生命周期 (Session Lifecycle);
2. 调度 MediaPipe Tasks Pose (P1) -> QualityGate (P1) -> 1€ Filter & FSM (P2) -> Assessment (P3) 的 O(1) 增量因果流水线;
3. 严格守护时间戳单调递增属性，自适应平滑时钟漂移与网络抖动;
4. 毫秒级返回骨架关键点、实时膝角/前倾角、FSM 状态与累加计数;
5. 会话结束时自动打包结构化时序记录并持久化，支持在“我的分析”中无缝回溯。
"""

import os
import cv2
import time
import uuid
import json
import logging
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

import numpy as np

from p1_pipeline.engine.tasks_adapter import MediaPipeTasksPoseEngine
from p1_pipeline.quality_gate import QualityGate
from p1_pipeline.contracts import OverlayStatus, PoseStatus, Side
from p2_temporal.runner import P2TemporalPipeline
from p2_temporal.contracts import RepetitionEvent, RepetitionRecord, FsmState
from p2_temporal.analytics import MultiRepAnalyticsEngine
from p3_rules.engine import SquatAssessmentEngine
from p3_rules.contracts import AssessmentStatus, RuleCardConfig

logger = logging.getLogger("web_demo.live_manager")


class LiveStreamSession:
    """单一摄像头实时流处理会话实例 (线程安全)"""

    def __init__(
        self,
        session_id: str,
        repo_root: Path,
        model_path: Optional[Path] = None,
    ):
        self.session_id = session_id
        self.repo_root = repo_root
        self.model_path = model_path or (self.repo_root / "models" / "pose_landmarker_full.task")
        self.lock = threading.Lock()

        # 核心算法引擎实例化
        self.pose_engine = MediaPipeTasksPoseEngine(
            model_path=str(self.model_path.resolve()),
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.pose_engine.initialize()

        self.quality_gate = QualityGate(calibration_window_frames=10)
        self.temporal_pipeline = P2TemporalPipeline()
        self.assessment_engine = SquatAssessmentEngine()

        # 会话时序状态
        self.created_at = time.time()
        self.last_active_at = time.time()
        self.frame_index = 0
        self.start_timestamp_ms: Optional[int] = None
        self.last_timestamp_ms: Optional[int] = None
        self.is_active = True

        # 时序遥测缓存 (内存留存用于实时曲线追加与结束归档)
        self.telemetry_history: List[Dict[str, Any]] = []
        self.completed_reps_assessment: List[Dict[str, Any]] = []

    def process_frame(
        self,
        image_bytes: bytes,
        client_timestamp_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        处理单帧摄像头图像并返回毫秒级实时运动学生理指标与骨骼点
        :param image_bytes: JPEG / PNG / WebP 二进制数据
        :param client_timestamp_ms: 前端客户端时间戳 (可选)
        :return: 实时帧分析结果字典
        """
        with self.lock:
            if not self.is_active:
                return {"error": "Session is closed", "is_valid": False}

            self.last_active_at = time.time()
            self.frame_index += 1

            # 1. 图像解码 (OpenCV 内存高速解码)
            nparr = np.frombuffer(image_bytes, np.uint8)
            bgr_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if bgr_img is None:
                return {
                    "frame_index": self.frame_index,
                    "error": "Failed to decode image frame",
                    "is_valid": False,
                }

            rgb_img = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2RGB)

            # 2. 单调递增时钟防护 (Monotonic Clock Guard)
            # 严格防止由于网络乱序或客户端时钟抖动导致传给 MediaPipe 的时间戳非单调递增
            now_ms = int(time.time() * 1000)
            if self.start_timestamp_ms is None:
                self.start_timestamp_ms = now_ms

            target_ts_ms = client_timestamp_ms if client_timestamp_ms else now_ms
            if self.last_timestamp_ms is not None and target_ts_ms <= self.last_timestamp_ms:
                target_ts_ms = self.last_timestamp_ms + 1

            self.last_timestamp_ms = target_ts_ms
            timestamp_us = target_ts_ms * 1000
            time_s = round((target_ts_ms - self.start_timestamp_ms) / 1000.0, 3)

            # 3. P1 MediaPipe 姿态提取
            pose_res = self.pose_engine.infer_frame(rgb_img, timestamp_us)
            landmarks_raw = pose_res.landmarks_2d

            # 4. P1 质量门控
            quality = self.quality_gate.evaluate(pose_res)
            is_frame_valid = (quality.overlay_status == OverlayStatus.DRAWABLE)
            active_side = quality.required_side.value if quality.required_side else "LEFT"

            # 5. P2 时序滤波与状态机推进
            p2_res = self.temporal_pipeline.process_frame(
                frame_index=self.frame_index,
                timeline_us=timestamp_us,
                landmarks_2d=landmarks_raw,
                side=active_side,
                is_frame_valid=is_frame_valid,
            )

            # 6. 导出供前端 Canvas 绘制的 33 关键点列表 [x, y, visibility]
            landmarks_export = []
            for lm in landmarks_raw:
                landmarks_export.append([
                    round(float(lm.x), 4),
                    round(float(lm.y), 4),
                    round(float(lm.visibility if lm.visibility is not None else 0.85), 3),
                ])

            # 7. 动作完成检测与 P3 实时规则评估
            rep_event_info = None
            if p2_res.event == RepetitionEvent.REP_COMPLETED:
                completed_records = [
                    r for r in self.temporal_pipeline.counter.records if r.status == "COMPLETED"
                ]
                if completed_records:
                    latest_rep = completed_records[-1]
                    assessment = self.assessment_engine.evaluate_repetition(latest_rep)
                    rep_event_info = {
                        "rep_id": latest_rep.rep_id,
                        "status": assessment.overall_status.value,
                        "min_knee_angle": round(latest_rep.min_knee_angle, 1),
                        "max_torso_angle": round(latest_rep.max_torso_lean_angle, 1),
                        "duration_s": round(latest_rep.duration_ms / 1000.0, 2),
                        "primary_reason": assessment.primary_reason,
                        "feedback": assessment.feedback_summary,
                    }
                    self.completed_reps_assessment.append(rep_event_info)

            # 8. 构造时序遥测快照
            telemetry_point = {
                "frame_index": self.frame_index,
                "time_s": time_s,
                "timestamp_ms": target_ts_ms,
                "is_valid": bool(p2_res.kinematics.is_valid),
                "gate_status": quality.overlay_status.value,
                "fsm_state": p2_res.fsm_state.value,
                "count": p2_res.cumulative_rep_count,
                "knee_angle": round(float(p2_res.kinematics.filtered_knee_angle), 1),
                "torso_angle": round(float(p2_res.kinematics.filtered_torso_angle), 1),
                "knee_velocity": round(float(p2_res.kinematics.knee_angular_velocity), 1),
                "torso_velocity": round(float(p2_res.kinematics.torso_angular_velocity), 1),
                "landmarks": landmarks_export,
                "rep_event": rep_event_info,
            }

            self.telemetry_history.append(telemetry_point)
            return telemetry_point

    def stop(self) -> Dict[str, Any]:
        """
        结束实时流会话，释放模型硬件句柄，并聚合全会话指标
        """
        with self.lock:
            if not self.is_active:
                return {"message": "Session already closed"}

            self.is_active = False

            # 安全关闭底层模型
            try:
                if hasattr(self.pose_engine, "landmarker") and self.pose_engine.landmarker:
                    self.pose_engine.landmarker.close()
            except Exception as e:
                logger.warning(f"Error closing landmarker in session {self.session_id}: {e}")

            # 统计汇总
            duration_s = round(time.time() - self.created_at, 2)
            total_reps = len(self.completed_reps_assessment)
            acceptable_reps = sum(
                1 for r in self.completed_reps_assessment if r["status"] == "ACCEPTABLE"
            )

            # 聚合评估结论
            if total_reps == 0:
                overall_status = "NOT_EVALUATED"
                overall_reason = "NO_COMPLETED_REPS"
                summary_guidance = "本次摄像头会话中未检测到完整的深蹲动作闭环（要求完成 下蹲->波谷->站起 完整周期）。"
            elif acceptable_reps == total_reps:
                overall_status = "ACCEPTABLE"
                overall_reason = "PASS"
                summary_guidance = f"太棒了！本次实时训练共完成 {total_reps} 次深蹲，动作深度充分且躯干稳定，各项生化力学指标均达标。"
            else:
                overall_status = "NEEDS_IMPROVEMENT"
                defects = []
                for r in self.completed_reps_assessment:
                    if r["status"] != "ACCEPTABLE" and r["primary_reason"]:
                        defects.append(r["primary_reason"])
                overall_reason = defects[0] if defects else "FORM_DEFECT"
                summary_guidance = f"本次训练完成 {total_reps} 次深蹲（其中 {acceptable_reps} 次达标）。请注意控制下蹲深度与躯干前倾幅度。"

            completed_records = [
                r for r in self.temporal_pipeline.counter.records if r.status == "COMPLETED" or r.is_valid
            ]
            multi_rep_summary = MultiRepAnalyticsEngine.analyze(
                completed_records, self.completed_reps_assessment
            ).to_dict()

            summary = {
                "session_id": self.session_id,
                "case_id": f"live_{self.session_id}",
                "case_name": f"实时摄像头分析 #{self.session_id[:6]}",
                "description": f"来自用户实时硬件摄像头流，共计追踪 {self.frame_index} 帧，耗时 {duration_s} 秒",
                "created_at": self.created_at,
                "duration_s": duration_s,
                "total_frames": self.frame_index,
                "total_reps": total_reps,
                "actual_count": total_reps,
                "actual_status": overall_status,
                "actual_primary_reason": overall_reason,
                "camera_view": "LIVE_WEBCAM",
                "verification_status": "PASS" if overall_status == "ACCEPTABLE" else "EVALUATED",
                "reps": self.completed_reps_assessment,
                "repetitions": [r.to_dict() for r in completed_records],
                "multi_rep_summary": multi_rep_summary,
                "summary_guidance": summary_guidance,
                "has_video": False,
                "video_url": None,
                "telemetry": self.telemetry_history,
                "metrics_summary": {
                    "total_reps": total_reps,
                    "acceptable_reps": acceptable_reps,
                    "duration_s": duration_s,
                    "processed_fps": round(self.frame_index / max(0.1, duration_s), 1),
                },
            }

            # 自动持久化至 reports/uploaded_demo/ 以便在前端“我的分析”中随时回放时序
            self._persist_session(summary)
            return summary

    def _persist_session(self, summary: Dict[str, Any]) -> None:
        """持久化会话摘要与逐帧遥测数据"""
        try:
            work_root = self.repo_root / "reports" / "uploaded_demo"
            summary_dir = work_root / "summaries"
            sidecar_dir = work_root / "sidecars"
            summary_dir.mkdir(parents=True, exist_ok=True)
            sidecar_dir.mkdir(parents=True, exist_ok=True)

            cid = summary["case_id"]
            summary_path = summary_dir / f"{cid}_summary.json"
            telemetry_path = sidecar_dir / f"{cid}_telemetry.json"

            # 写入总结 JSON
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)

            # 写入时序遥测 JSON
            with open(telemetry_path, "w", encoding="utf-8") as f:
                json.dump(self.telemetry_history, f, ensure_ascii=False, indent=2)

            logger.info(f"Live session {self.session_id} persisted to {summary_path}")
        except Exception as e:
            logger.error(f"Failed to persist live session {self.session_id}: {e}")


class LiveStreamManager:
    """实时视频流多会话生命周期调度中心 (线程安全)"""

    MAX_ACTIVE_SESSIONS = 10
    SESSION_IDLE_TIMEOUT_S = 300.0  # 5分钟无帧输入自动清理

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = Path(repo_root) if repo_root else Path(__file__).resolve().parent.parent
        self.model_path = self.repo_root / "models" / "pose_landmarker_full.task"
        self.sessions: Dict[str, LiveStreamSession] = {}
        self.lock = threading.Lock()

    def create_session(self) -> LiveStreamSession:
        """创建并激活一个新实时流会话"""
        with self.lock:
            self._cleanup_stale_sessions()

            if len(self.sessions) >= self.MAX_ACTIVE_SESSIONS:
                # 剔除最久未活动的会话
                oldest_sid = min(self.sessions.keys(), key=lambda k: self.sessions[k].last_active_at)
                logger.info(f"Evicting oldest live session: {oldest_sid}")
                self._stop_and_remove(oldest_sid)

            session_id = uuid.uuid4().hex[:12]
            session = LiveStreamSession(
                session_id=session_id,
                repo_root=self.repo_root,
                model_path=self.model_path,
            )
            self.sessions[session_id] = session
            logger.info(f"Created live session: {session_id} (active: {len(self.sessions)})")
            return session

    def get_session(self, session_id: str) -> Optional[LiveStreamSession]:
        """获取指定会话句柄"""
        with self.lock:
            return self.sessions.get(session_id)

    def close_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """结束指定会话并回收资源"""
        with self.lock:
            return self._stop_and_remove(session_id)

    def _stop_and_remove(self, session_id: str) -> Optional[Dict[str, Any]]:
        session = self.sessions.pop(session_id, None)
        if session:
            summary = session.stop()
            logger.info(f"Closed live session: {session_id}")
            return summary
        return None

    def cleanup_idle_sessions(self, timeout_sec: Optional[float] = None) -> int:
        """
        显式扫描并清理超时闲置会话 (高可用防护)
        :param timeout_sec: 自定义闲置超时秒数，不填则使用默认值
        :return: 成功清理回收的会话总数
        """
        with self.lock:
            now = time.time()
            limit = timeout_sec if timeout_sec is not None else self.SESSION_IDLE_TIMEOUT_S
            stale_sids = [
                sid
                for sid, sess in self.sessions.items()
                if (now - sess.last_active_at) > limit
            ]
            count = 0
            for sid in stale_sids:
                logger.info(f"Cleaning up stale live session {sid} (idle > {limit}s)")
                if self._stop_and_remove(sid):
                    count += 1
            return count

    def _cleanup_stale_sessions(self) -> None:
        """内部清理超时闲置会话"""
        now = time.time()
        stale_sids = [
            sid
            for sid, sess in self.sessions.items()
            if (now - sess.last_active_at) > self.SESSION_IDLE_TIMEOUT_S
        ]
        for sid in stale_sids:
            logger.info(f"Cleaning up stale live session {sid} (idle > {self.SESSION_IDLE_TIMEOUT_S}s)")
            self._stop_and_remove(sid)
