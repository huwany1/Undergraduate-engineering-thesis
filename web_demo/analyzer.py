# -*- coding: utf-8 -*-
"""
在线视频分析生命周期与调度管理器 (Online Video Analysis Manager)
五大架构指标保障:
1. 高内聚 (High Cohesion): 剥离具体的底层模型与时序循环，委托给独立 InferenceTaskWorker;
2. 高可用 (High Availability): 管理并发任务队列配额，支持超时看门狗与任务主动取消;
3. 线程安全 (Thread Safety): 严格互斥锁保护任务状态机与任务生命周期注册表.
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
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Optional, Tuple

from .worker import InferenceTaskWorker
from .hardware import AccelerationProfile, HardwareProfileManager

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
    worker: Optional[InferenceTaskWorker] = None


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
    """在线视频分析调度与任务生命周期管理器 (线程安全 & 高可用)"""

    MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
    MAX_RETAINED_TASKS = 50                 # 任务注册表最大留存
    MAX_CONCURRENT_WORKERS = 2              # 最大并发推理线程数
    DEFAULT_TIMEOUT_SEC = 60.0             # 单个任务超时熔断上限

    def __init__(
        self,
        repo_root: Optional[Path] = None,
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
        hardware_manager: Optional[HardwareProfileManager] = None,
    ):
        self.repo_root = Path(repo_root) if repo_root else Path(__file__).resolve().parent.parent
        self.work_root = self.repo_root / "reports" / "uploaded_demo"
        self.upload_dir = self.work_root / "uploads"
        self.screenshot_dir = self.work_root / "screenshots"
        self.sidecar_dir = self.work_root / "sidecars"
        self.summary_dir = self.work_root / "summaries"
        self.model_path = self.repo_root / "models" / "pose_landmarker_full.task"
        self.timeout_sec = timeout_sec
        self.hardware_manager = hardware_manager

        # 创建目录结构
        for d in (self.upload_dir, self.screenshot_dir, self.sidecar_dir, self.summary_dir):
            d.mkdir(parents=True, exist_ok=True)

        self._tasks: Dict[str, AnalysisTask] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=self.MAX_CONCURRENT_WORKERS,
            thread_name_prefix="OnlineAnalysisWorker",
        )

    def submit_video(
        self,
        file_bytes: bytes,
        original_filename: str,
        acceleration_profile: Optional[AccelerationProfile] = None,
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

        # 决定生效的算力模式
        eff_profile = acceleration_profile
        if eff_profile is None and self.hardware_manager:
            eff_profile = self.hardware_manager.current_profile
        if eff_profile is None:
            eff_profile = AccelerationProfile.CPU_HIGH_PERF

        # 实例化独立的 InferenceTaskWorker
        worker = InferenceTaskWorker(
            task_id=task_id,
            video_path=saved_video_path,
            original_filename=original_filename,
            model_path=self.model_path,
            screenshot_dir=self.screenshot_dir,
            sidecar_dir=self.sidecar_dir,
            summary_dir=self.summary_dir,
            repo_root=self.repo_root,
            timeout_sec=self.timeout_sec,
            acceleration_profile=eff_profile,
        )

        task = AnalysisTask(
            task_id=task_id,
            status=AnalysisTaskStatus.PENDING,
            progress=0,
            stage_name="视频上传成功，正在排队启动流水线...",
            created_at=time.time(),
            video_filename=original_filename,
            video_rel_path=str(saved_video_path.relative_to(self.repo_root)).replace("\\", "/"),
            worker=worker,
        )

        with self._lock:
            # 清理历史旧任务
            if len(self._tasks) >= self.MAX_RETAINED_TASKS:
                oldest_id = min(self._tasks.keys(), key=lambda k: self._tasks[k].created_at)
                del self._tasks[oldest_id]
            self._tasks[task_id] = task

        # 提交到后台线程池由 Worker 执行
        self._executor.submit(self._dispatch_worker, task_id, worker)
        return task_id

    def cancel_task(self, task_id: str) -> bool:
        """取消正在运行或排队中的分析任务"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            if task.worker:
                task.worker.cancel()
            task.status = AnalysisTaskStatus.FAILED
            task.error = "任务已被用户取消"
            task.stage_name = "任务已取消"
            return True

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
            completed.sort(key=lambda x: x["created_at"], reverse=True)
            return completed

    def _dispatch_worker(self, task_id: str, worker: InferenceTaskWorker) -> None:
        """在工作线程中调度执行 InferenceTaskWorker"""
        task = self.get_task(task_id)
        if not task:
            return

        def on_progress(pct: int, msg: str):
            task.status = AnalysisTaskStatus.PROCESSING
            task.progress = pct
            task.stage_name = msg

        try:
            task.status = AnalysisTaskStatus.PROCESSING
            report_result = worker.execute(progress_callback=on_progress)
            task.result = report_result
            task.progress = 100
            task.status = AnalysisTaskStatus.COMPLETED
            task.stage_name = "分析完成！专属报告与回放曲线已就绪。"
            logger.info(f"Task {task_id} successfully processed by worker")
        except Exception as e:
            logger.exception(f"Task {task_id} execution failed: {e}")
            task.status = AnalysisTaskStatus.FAILED
            task.error = str(e)
            task.stage_name = f"处理失败: {str(e)}"
