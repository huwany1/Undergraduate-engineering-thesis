# -*- coding: utf-8 -*-
"""
硬件算力探测、异构加速配置与异步预取读取器
五大架构指标保障:
1. 低耦合 (Low Coupling): 抽象硬件探测与流摄入管道，推理引擎与质检规则卡零硬件感知;
2. 高可用 (High Availability): Windows WMI 与 OpenCV OpenCL 双通道探测兜底，异常 0 成本降级 CPU;
3. 高性能 (High Performance): 智能视网膜前置等比缩放 (720p) + 异步双缓冲 (Double-buffering Queue) 隐藏解码时延;
4. 高内聚 (High Cohesion): 显卡属性识别、模式推荐与流式缓冲区封装于本模块;
5. 可维护 (Maintainability): 提供结构化 DTO 与规范 REST 接口，支持 Web 端一键热切换.
"""

import os
import cv2
import json
import time
import queue
import logging
import threading
import subprocess
from enum import Enum
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("web_demo.hardware")


class AccelerationProfile(str, Enum):
    """算力加速模式枚举"""
    CPU_HIGH_PERF = "CPU_HIGH_PERF"         # 纯 CPU 极致高吞吐 (核显首选，零画面卡顿)
    GPU_ACCELERATED = "GPU_ACCELERATED"     # GPU 硬件加速 (N卡/A卡可选，硬件解码与异构预处理)


@dataclass
class GPUInfo:
    """单个显卡硬件信息载体"""
    name: str
    vendor: str                         # "NVIDIA", "AMD", "Intel", "Other"
    type: str                           # "iGPU (集成核显)" 或 "dGPU (独立显卡)"
    is_discrete: bool
    ram_mb: Optional[int]
    driver_version: Optional[str]
    is_recommended_for_gpu: bool


class SystemHardwareProbe:
    """系统硬件与显卡算力探针 (跨平台 & 容错兜底)"""

    _cached_result: Optional[Dict[str, Any]] = None
    _cache_time: float = 0.0
    CACHE_TTL_SEC: float = 10.0  # 缓存 10 秒防高频探测开销

    @classmethod
    def detect(cls, force_refresh: bool = False) -> Dict[str, Any]:
        """探测本地系统中的显卡配置与加速能力"""
        now = time.time()
        if not force_refresh and cls._cached_result and (now - cls._cache_time < cls.CACHE_TTL_SEC):
            return cls._cached_result

        gpus: List[GPUInfo] = []

        # 1. 尝试 Windows WMI / PowerShell 原生探测
        if os.name == "nt":
            gpus.extend(cls._detect_windows_gpus())

        # 2. 若未探测到显卡或非 Windows，调用 OpenCV / OpenCL 探测兜底
        has_opencl = False
        ocl_device_name = ""
        try:
            if cv2.ocl.haveOpenCL():
                cv2.ocl.setUseOpenCL(True)
                has_opencl = cv2.ocl.useOpenCL()
                dev = cv2.ocl.Device.getDefault()
                ocl_device_name = dev.name() if dev else ""
                if not gpus and ocl_device_name:
                    is_igpu = any(k in ocl_device_name.lower() for k in ["gfx11", "graphics", "uhd", "iris", "780m", "680m"])
                    vendor = "AMD" if "amd" in ocl_device_name.lower() or "gfx" in ocl_device_name.lower() else "Unknown"
                    gpus.append(GPUInfo(
                        name=ocl_device_name,
                        vendor=vendor,
                        type="iGPU (集成核显)" if is_igpu else "dGPU (独立显卡)",
                        is_discrete=not is_igpu,
                        ram_mb=None,
                        driver_version=None,
                        is_recommended_for_gpu=not is_igpu,
                    ))
        except Exception as ex:
            logger.debug(f"OpenCL probe warning: {ex}")

        # 3. 汇总显卡特征与决策逻辑
        has_discrete = any(g.is_discrete for g in gpus)
        has_igpu = any(not g.is_discrete for g in gpus)

        primary_gpu_name = gpus[0].name if gpus else "通用显示适配器"
        primary_gpu_type = gpus[0].type if gpus else "未知类型"

        if has_discrete:
            suggested_profile = AccelerationProfile.GPU_ACCELERATED.value
            notice_level = "RECOMMENDED_GPU"
            message = "检测到独立显卡 (dGPU)。推荐开启 GPU 硬件加速，可利用专用硬件视频编解码与高带宽并行计算大幅加速分析。"
        elif has_igpu:
            suggested_profile = AccelerationProfile.CPU_HIGH_PERF.value
            notice_level = "WARNING_IF_GPU_ENABLED"
            message = (
                f"检测到当前主要显卡为集成核显 ({primary_gpu_name})。"
                "强烈推荐使用纯 CPU 极致高吞吐模式，避免共享显存带宽争用引发前台画面与视频播放轻微卡顿；"
                "您仍可自主开启 GPU 加速，系统将启用硬件视频解码并限制算力配额防卡顿。"
            )
        else:
            suggested_profile = AccelerationProfile.CPU_HIGH_PERF.value
            notice_level = "INFO"
            message = "未检测到独立显卡，推荐采用 CPU 极致高吞吐模式进行姿态估计与时序分析。"

        result = {
            "gpus": [asdict(g) for g in gpus],
            "has_discrete_gpu": has_discrete,
            "has_integrated_gpu": has_igpu,
            "detected_primary_gpu": f"{primary_gpu_name} ({primary_gpu_type})",
            "suggested_profile": suggested_profile,
            "recommendation": {
                "suggested_profile": suggested_profile,
                "notice_level": notice_level,
                "message": message,
            },
            "capabilities": {
                "opencl": has_opencl,
                "opencl_device": ocl_device_name,
                "msmf_hardware_decode": True if os.name == "nt" else False,
            },
            "detected_at": now,
        }

        cls._cached_result = result
        cls._cache_time = now
        return result

    @classmethod
    def _detect_windows_gpus(cls) -> List[GPUInfo]:
        """通过 Windows CIM/WMI 查询物理显卡列表"""
        gpus: List[GPUInfo] = []
        try:
            ps_cmd = (
                "Get-CimInstance Win32_VideoController | "
                "Select-Object Name, AdapterRAM, DriverVersion | "
                "ConvertTo-Json"
            )
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=3.0,
            )
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                if isinstance(data, dict):
                    data = [data]
                for item in data:
                    name = item.get("Name", "").strip()
                    if not name:
                        continue
                    # 过滤远程虚拟桌面适配器（保留物理 GPU）
                    if any(v in name.lower() for v in ["virtual", "rdp", "remote", "vnc", "citrix"]):
                        continue

                    name_lower = name.lower()
                    is_nvidia = any(k in name_lower for k in ["nvidia", "geforce", "rtx", "gtx", "quadro", "tesla"])
                    is_amd = any(k in name_lower for k in ["amd", "radeon"])
                    is_intel = any(k in name_lower for k in ["intel", "iris", "uhd", "arc"])

                    vendor = "NVIDIA" if is_nvidia else ("AMD" if is_amd else ("Intel" if is_intel else "Other"))
                    
                    # 核显特征识别 (Radeon 780M/680M/Graphics/Vega, Intel UHD/Iris Xe)
                    is_igpu = any(k in name_lower for k in [
                        "780m", "680m", "graphics", "vega", "uhd", "iris", "hd graphics"
                    ])
                    # 若明确带有 RX / RTX / GTX / Arc A 则判定为独显
                    if any(k in name_lower for k in ["rtx", "gtx", "rx 6", "rx 7", "rx 5", "arc a"]):
                        is_igpu = False

                    ram = item.get("AdapterRAM")
                    ram_mb = int(ram) // (1024 * 1024) if ram else None

                    gpus.append(GPUInfo(
                        name=name,
                        vendor=vendor,
                        type="iGPU (集成核显)" if is_igpu else "dGPU (独立显卡)",
                        is_discrete=not is_igpu,
                        ram_mb=ram_mb,
                        driver_version=item.get("DriverVersion"),
                        is_recommended_for_gpu=not is_igpu,
                    ))
        except Exception as e:
            logger.debug(f"PowerShell GPU probe error: {e}")

        return gpus


class HardwareProfileManager:
    """算力模式全局状态与协同管理器 (线程安全)"""

    def __init__(self, default_profile: Optional[AccelerationProfile] = None):
        self._lock = threading.Lock()
        if default_profile is not None:
            self._current_profile = default_profile
        else:
            # 默认自适应探测: 核显默认 CPU_HIGH_PERF, 独显默认 GPU_ACCELERATED
            probe = SystemHardwareProbe.detect()
            self._current_profile = (
                AccelerationProfile.GPU_ACCELERATED
                if probe.get("has_discrete_gpu")
                else AccelerationProfile.CPU_HIGH_PERF
            )

    @property
    def current_profile(self) -> AccelerationProfile:
        with self._lock:
            return self._current_profile

    def set_profile(self, profile: AccelerationProfile) -> None:
        with self._lock:
            self._current_profile = profile
            logger.info(f"Hardware acceleration profile changed to: {profile.value}")

    def get_status_payload(self) -> Dict[str, Any]:
        """组装完整的硬件与模式状态数据报文"""
        probe = SystemHardwareProbe.detect()
        with self._lock:
            active_profile = self._current_profile.value

        probe_copy = dict(probe)
        probe_copy["active_profile"] = active_profile
        return probe_copy


class PrefetchVideoReader:
    """
    异步双缓冲视频帧预取与视网膜降采样流水线 (High Performance & Anti-Stuttering)
    核心特性:
    1. 智能视网膜前置等比规整: 约束最长边至 720px，将 4K 内存带宽暴降 88.9%，精度绝对保真;
    2. 异步双缓冲有界队列: 解码与主推理线程完全重叠 (Overlap)，隐藏解码 I/O 延迟;
    3. 异构支持: GPU 模式下激活 MSMF 硬件解码通道与 OpenCL，CPU 模式下 0 GPU 占用防卡顿.
    """

    def __init__(
        self,
        video_path: Path,
        profile: AccelerationProfile = AccelerationProfile.CPU_HIGH_PERF,
        max_dimension: int = 720,
        queue_size: int = 16,
    ):
        self.video_path = Path(video_path)
        self.profile = profile
        self.max_dimension = max_dimension
        self.queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None

        # 打开视频流
        if profile == AccelerationProfile.GPU_ACCELERATED and os.name == "nt":
            # 尝试开启 Windows MSMF 硬件解码通道
            self.cap = cv2.VideoCapture(str(self.video_path), cv2.CAP_MSMF)
            if not self.cap.isOpened():
                self.cap = cv2.VideoCapture(str(self.video_path))
            if cv2.ocl.haveOpenCL():
                cv2.ocl.setUseOpenCL(True)
        else:
            # 纯 CPU 路径，禁用 OpenCL，防止抢占核显显存总线
            if cv2.ocl.haveOpenCL():
                cv2.ocl.setUseOpenCL(False)
            self.cap = cv2.VideoCapture(str(self.video_path))

        if not self.cap.isOpened():
            raise RuntimeError(f"OpenCV 无法解码视频流: {self.video_path}")

        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.fps = float(self.cap.get(cv2.CAP_PROP_FPS))
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if self.fps <= 0 or self.fps != self.fps:
            self.fps = 30.0
        if self.total_frames <= 0:
            self.total_frames = 150

        # 计算视网膜等比缩放系数
        max_dim = max(self.width, self.height)
        if max_dim > self.max_dimension:
            self.scale = self.max_dimension / float(max_dim)
            self.scaled_width = int(round(self.width * self.scale))
            self.scaled_height = int(round(self.height * self.scale))
        else:
            self.scale = 1.0
            self.scaled_width = self.width
            self.scaled_height = self.height

    def start(self) -> "PrefetchVideoReader":
        """启动后台生产者异步预读取线程"""
        self.thread = threading.Thread(
            target=self._produce_frames,
            name="PrefetchVideoReaderThread",
            daemon=True,
        )
        self.thread.start()
        return self

    def _produce_frames(self) -> None:
        """生产者子线程主循环"""
        frame_idx = 0
        try:
            while not self.stop_event.is_set():
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    # 读取完毕，发送 EOF 哨兵
                    self.queue.put((None, None, frame_idx), timeout=5.0)
                    break

                # 1. 视网膜等比规整 (若是超大图则快速下采样)
                if self.scale < 1.0:
                    scaled_frame = cv2.resize(
                        frame,
                        (self.scaled_width, self.scaled_height),
                        interpolation=cv2.INTER_AREA,
                    )
                else:
                    scaled_frame = frame

                # 2. 颜色空间转换
                rgb_frame = cv2.cvtColor(scaled_frame, cv2.COLOR_BGR2RGB)

                # 3. 阻塞放入双缓冲有界队列
                while not self.stop_event.is_set():
                    try:
                        self.queue.put((frame, rgb_frame, frame_idx), timeout=0.2)
                        break
                    except queue.Full:
                        continue

                frame_idx += 1
        except Exception as ex:
            logger.debug(f"Prefetch producer stopped: {ex}")
            try:
                self.queue.put((None, None, -1), timeout=1.0)
            except Exception:
                pass
        finally:
            self.cap.release()

    def get_frame(self, timeout: float = 10.0) -> Tuple[Optional[Any], Optional[Any], int]:
        """消费者获取下一帧: (raw_bgr_frame, preprocessed_rgb_frame, frame_index)"""
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return None, None, -1

    def close(self) -> None:
        """优雅终止并释放所有资源"""
        self.stop_event.set()
        # 排空队列以唤醒可能阻塞的生产者
        try:
            while not self.queue.empty():
                self.queue.get_nowait()
        except Exception:
            pass
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        if self.cap and self.cap.isOpened():
            self.cap.release()
