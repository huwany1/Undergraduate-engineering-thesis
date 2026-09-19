# -*- coding: utf-8 -*-
"""
硬件算力探测、异构加速模式与异步双缓冲流水线回归测试套件
依据: AGENTS.md / GEMINI.md 核心规范
指标保障: 高可用 (容错降级)、高性能 (视网膜预缩放 & 预取)、低耦合 (模块独立测试)
"""

import os
import cv2
import json
import time
import pytest
import urllib.request
import urllib.error
from pathlib import Path

from web_demo.hardware import (
    SystemHardwareProbe,
    HardwareProfileManager,
    AccelerationProfile,
    PrefetchVideoReader,
)
from web_demo.service import DemoService
from web_demo.server import run_server


@pytest.fixture(scope="module")
def repo_root():
    return Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def test_video_path(repo_root):
    # 使用测试视频资源
    candidates = [
        repo_root / "reports" / "uploaded_demo" / "uploads" / "up_5eb18d2fcc_4065452-uhd_3840_216.mp4",
        repo_root / "reports" / "validation_package" / "replays" / "TC01_PERFECT_SQUAT_annotated.mp4",
    ]
    for p in candidates:
        if p.exists():
            return p
    # 兜底生成一个极简临时测试视频
    tmp_path = repo_root / "reports" / "uploaded_demo" / "uploads" / "tmp_test_synth.mp4"
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(tmp_path), fourcc, 30.0, (1920, 1080))
    import numpy as np
    for _ in range(15):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        out.write(frame)
    out.release()
    return tmp_path


class TestHardwareProbe:
    """硬件探针单元测试"""

    def test_probe_returns_valid_structure(self):
        probe = SystemHardwareProbe.detect(force_refresh=True)
        assert isinstance(probe, dict)
        assert "gpus" in probe
        assert "has_discrete_gpu" in probe
        assert "has_integrated_gpu" in probe
        assert "detected_primary_gpu" in probe
        assert "suggested_profile" in probe
        assert "recommendation" in probe
        assert "capabilities" in probe

        rec = probe["recommendation"]
        assert "suggested_profile" in rec
        assert "notice_level" in rec
        assert "message" in rec
        assert len(rec["message"]) > 0

        cap = probe["capabilities"]
        assert "opencl" in cap

    def test_probe_cache_ttl(self):
        res1 = SystemHardwareProbe.detect(force_refresh=False)
        res2 = SystemHardwareProbe.detect(force_refresh=False)
        assert res1["detected_at"] == res2["detected_at"]


class TestHardwareProfileManager:
    """算力配置管理器状态机测试"""

    def test_default_profile_lifecycle(self):
        mgr = HardwareProfileManager(default_profile=AccelerationProfile.CPU_HIGH_PERF)
        assert mgr.current_profile == AccelerationProfile.CPU_HIGH_PERF

        mgr.set_profile(AccelerationProfile.GPU_ACCELERATED)
        assert mgr.current_profile == AccelerationProfile.GPU_ACCELERATED

        payload = mgr.get_status_payload()
        assert payload["active_profile"] == "GPU_ACCELERATED"

    def test_service_profile_switching(self, repo_root):
        service = DemoService(repo_root=repo_root)
        status_init = service.get_hardware_status()
        assert "active_profile" in status_init

        # 切换到 CPU 模式
        res = service.set_hardware_profile("CPU_HIGH_PERF")
        assert res["active_profile"] == "CPU_HIGH_PERF"
        assert service.hardware_manager.current_profile == AccelerationProfile.CPU_HIGH_PERF

        # 切换到 GPU 模式
        res = service.set_hardware_profile("GPU_ACCELERATED")
        assert res["active_profile"] == "GPU_ACCELERATED"

        # 非法模式抛异常
        with pytest.raises(ValueError):
            service.set_hardware_profile("QUANTUM_COMPUTING")


class TestPrefetchVideoReader:
    """异步双缓冲预取与视网膜降采样流水线测试"""

    def test_reader_downscaling_and_queue(self, test_video_path):
        reader = PrefetchVideoReader(
            video_path=test_video_path,
            profile=AccelerationProfile.CPU_HIGH_PERF,
            max_dimension=720,
            queue_size=8,
        ).start()

        assert reader.fps > 0
        assert reader.total_frames > 0
        # 尺寸最长边必须 <= 720
        assert max(reader.scaled_width, reader.scaled_height) <= 720

        frames_read = 0
        while True:
            raw_frame, rgb_frame, idx = reader.get_frame(timeout=3.0)
            if raw_frame is None or rgb_frame is None:
                break
            assert rgb_frame.shape[0] == reader.scaled_height
            assert rgb_frame.shape[1] == reader.scaled_width
            assert rgb_frame.shape[2] == 3
            frames_read += 1
            if frames_read >= 10:
                break

        reader.close()
        assert frames_read >= 5


class TestHardwareRestApi:
    """Web 服务硬件加速 REST API 测试"""

    @pytest.fixture(scope="class")
    def live_server(self, repo_root):
        server = run_server(port=8089, host="127.0.0.1", repo_root=repo_root)
        import threading
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        time.sleep(0.5)
        yield "http://127.0.0.1:8089"
        server.shutdown()
        server.server_close()

    def test_get_hardware_endpoint(self, live_server):
        req = urllib.request.Request(f"{live_server}/api/system/hardware")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert "gpus" in data
            assert "active_profile" in data
            assert "recommendation" in data

    def test_post_hardware_profile_endpoint(self, live_server):
        # 1. 切换为 CPU_HIGH_PERF
        body = json.dumps({"profile": "CPU_HIGH_PERF"}).encode("utf-8")
        req = urllib.request.Request(
            f"{live_server}/api/system/hardware/profile",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["active_profile"] == "CPU_HIGH_PERF"

        # 2. 切换为 GPU_ACCELERATED
        body = json.dumps({"profile": "GPU_ACCELERATED"}).encode("utf-8")
        req = urllib.request.Request(
            f"{live_server}/api/system/hardware/profile",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["active_profile"] == "GPU_ACCELERATED"

        # 3. 测试非法输入抛 400
        bad_body = json.dumps({"profile": "INVALID_PROFILE"}).encode("utf-8")
        bad_req = urllib.request.Request(
            f"{live_server}/api/system/hardware/profile",
            data=bad_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(bad_req, timeout=5)
        assert exc_info.value.code == 400
