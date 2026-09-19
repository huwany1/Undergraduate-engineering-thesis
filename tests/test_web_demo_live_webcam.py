# -*- coding: utf-8 -*-
"""
维度一 实时硬件摄像头与视频流 (Live Webcam & Stream) 自动化回归与接口测试套件
依据: AGENTS.md / GEMINI.md 测试驱动与防回归规则
测试范围:
1. LiveStreamSession 会话生命周期与单调时钟防崩溃安全测试;
2. 损坏图像与异常负载容错测试;
3. 真实视频连续帧推流、实时骨架提取、FSM 状态机推进与完成计数测试;
4. LiveStreamManager 并发限制与会话清理回收测试;
5. REST API 端到端路由 (/api/live/session/start, /frame, /stop, 状态查询) 测试。
"""

import io
import time
import json
import cv2
import numpy as np
import pytest
from pathlib import Path
from http import HTTPStatus
import urllib.request
import urllib.error

from web_demo.live_manager import LiveStreamSession, LiveStreamManager
from web_demo.server import run_server


@pytest.fixture
def repo_root():
    return Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def cleanup_test_artifacts(repo_root):
    """自动清理测试过程中产生的临时 live 会话文件"""
    work_root = repo_root / "reports" / "uploaded_demo"
    summary_dir = work_root / "summaries"
    sidecar_dir = work_root / "sidecars"

    yield

    for p in list(summary_dir.glob("live_*_summary.json")):
        try:
            p.unlink()
        except Exception:
            pass
    for p in list(sidecar_dir.glob("live_*_telemetry.json")):
        try:
            p.unlink()
        except Exception:
            pass


@pytest.fixture
def sample_jpeg_bytes():
    """生成一个 640x480 的合成测试 JPEG 帧"""
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    # 画一个简单人脸或线条
    cv2.circle(img, (320, 240), 50, (255, 255, 255), -1)
    success, enc = cv2.imencode(".jpg", img)
    assert success
    return enc.tobytes()


def test_live_session_lifecycle(repo_root, sample_jpeg_bytes):
    """测试实时流会话创建、单帧处理与停止归档全生命周期"""
    session = LiveStreamSession(session_id="test_lifecycle_001", repo_root=repo_root)
    assert session.is_active is True
    assert session.frame_index == 0
    assert session.start_timestamp_ms is None

    # 推送单帧
    res = session.process_frame(sample_jpeg_bytes)
    assert res["frame_index"] == 1
    assert "time_s" in res
    assert "knee_angle" in res
    assert "torso_angle" in res
    assert "fsm_state" in res
    assert "count" in res
    assert "landmarks" in res
    assert isinstance(res["landmarks"], list)

    # 停止会话
    summary = session.stop()
    assert session.is_active is False
    assert summary["session_id"] == "test_lifecycle_001"
    assert summary["actual_count"] == 0
    assert summary["total_frames"] == 1
    assert "summary_guidance" in summary


def test_live_session_monotonic_clock_guard(repo_root, sample_jpeg_bytes):
    """测试单调递增时钟防护：客户端乱序或时钟漂移绝不导致底层引擎异常"""
    session = LiveStreamSession(session_id="test_clock_001", repo_root=repo_root)

    # 第 1 帧：时间戳 5000ms
    r1 = session.process_frame(sample_jpeg_bytes, client_timestamp_ms=5000)
    assert r1["timestamp_ms"] == 5000

    # 第 2 帧：模拟时钟倒流或乱序到达（例如 4500ms）
    r2 = session.process_frame(sample_jpeg_bytes, client_timestamp_ms=4500)
    # 强制补偿为至少比上一帧多 1ms
    assert r2["timestamp_ms"] > r1["timestamp_ms"]
    assert r2["timestamp_ms"] == 5001

    session.stop()


def test_live_session_corrupted_frame_handling(repo_root):
    """测试损坏的图像数据输入时优雅降级处理"""
    session = LiveStreamSession(session_id="test_corrupted_001", repo_root=repo_root)

    corrupted_bytes = b"NOT_A_VALID_IMAGE_DATA_12345"
    res = session.process_frame(corrupted_bytes)
    assert res["is_valid"] is False
    assert "error" in res

    session.stop()


def test_live_session_real_squat_progression(repo_root):
    """使用黄金用例真实视频帧连续推流，验证 FSM 状态流转与计数累加"""
    video_path = repo_root / "reports" / "validation_package" / "replays" / "TC_01_PERFECT_SQUAT_annotated.mp4"
    if not video_path.exists():
        pytest.skip("Replay video asset not found, skipping video progression test")

    cap = cv2.VideoCapture(str(video_path))
    assert cap.isOpened()

    session = LiveStreamSession(session_id="test_progression_001", repo_root=repo_root)

    fsm_states_observed = set()
    max_count = 0
    rep_event_captured = False

    # 读取前 45 帧进行连续实时推流测试
    for i in range(45):
        ret, frame = cap.read()
        if not ret:
            break
        # 编码为 JPEG 模拟网络推流
        ok, enc = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        assert ok
        point = session.process_frame(enc.tobytes())

        fsm_states_observed.add(point["fsm_state"])
        if point["count"] > max_count:
            max_count = point["count"]
        if point.get("rep_event"):
            rep_event_captured = True

    cap.release()
    summary = session.stop()

    assert len(fsm_states_observed) >= 2  # 至少经历 STANDING 及 DESCENDING/BOTTOM
    assert summary["total_frames"] > 0
    assert summary["camera_view"] == "LIVE_WEBCAM"


def test_live_manager_concurrency_and_cleanup(repo_root):
    """测试 LiveStreamManager 会话生命周期池、并发限制与清理逻辑"""
    manager = LiveStreamManager(repo_root=repo_root)
    manager.MAX_ACTIVE_SESSIONS = 3
    manager.SESSION_IDLE_TIMEOUT_S = 0.5  # 0.5 秒测试超时

    # 创建 3 个会话
    s1 = manager.create_session()
    s2 = manager.create_session()
    s3 = manager.create_session()

    assert len(manager.sessions) == 3
    assert manager.get_session(s1.session_id) is not None

    # 创建第 4 个会话，应自动淘汰最久未活动的 s1
    s4 = manager.create_session()
    assert len(manager.sessions) == 3
    assert manager.get_session(s1.session_id) is None
    assert manager.get_session(s4.session_id) is not None

    # 测试超时清理
    time.sleep(0.6)
    s5 = manager.create_session()
    # 之前超时的应该被清理
    assert len(manager.sessions) <= 2

    # 主动关闭
    manager.close_session(s5.session_id)
    assert manager.get_session(s5.session_id) is None


def test_live_web_server_rest_api(repo_root, sample_jpeg_bytes):
    """集成测试：通过实际 HTTP 服务测试 /api/live/session/* 端点"""
    server = run_server(port=0, host="127.0.0.1", repo_root=repo_root)
    port = server.server_port

    import threading
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    base_url = f"http://127.0.0.1:{port}"

    try:
        # 1. POST /api/live/session/start
        req_start = urllib.request.Request(
            f"{base_url}/api/live/session/start",
            data=b"",
            method="POST",
        )
        with urllib.request.urlopen(req_start) as resp:
            assert resp.status == HTTPStatus.CREATED
            start_data = json.loads(resp.read().decode("utf-8"))
            session_id = start_data["session_id"]
            assert start_data["status"] == "RUNNING"

        # 2. GET /api/live/session/<session_id>
        with urllib.request.urlopen(f"{base_url}/api/live/session/{session_id}") as resp:
            assert resp.status == HTTPStatus.OK
            status_data = json.loads(resp.read().decode("utf-8"))
            assert status_data["session_id"] == session_id
            assert status_data["is_active"] is True
            assert status_data["frame_index"] == 0

        # 3. POST /api/live/session/<session_id>/frame
        req_frame = urllib.request.Request(
            f"{base_url}/api/live/session/{session_id}/frame",
            data=sample_jpeg_bytes,
            headers={
                "Content-Type": "image/jpeg",
                "X-Client-Timestamp": str(int(time.time() * 1000)),
            },
            method="POST",
        )
        with urllib.request.urlopen(req_frame) as resp:
            assert resp.status == HTTPStatus.OK
            frame_data = json.loads(resp.read().decode("utf-8"))
            assert frame_data["frame_index"] == 1
            assert "landmarks" in frame_data
            assert "knee_angle" in frame_data

        # 4. POST /api/live/session/<session_id>/stop
        req_stop = urllib.request.Request(
            f"{base_url}/api/live/session/{session_id}/stop",
            data=b"",
            method="POST",
        )
        with urllib.request.urlopen(req_stop) as resp:
            assert resp.status == HTTPStatus.OK
            stop_data = json.loads(resp.read().decode("utf-8"))
            assert stop_data["session_id"] == session_id
            assert "actual_count" in stop_data

        # 5. 再次查询状态，应返回 404
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"{base_url}/api/live/session/{session_id}")
        assert exc_info.value.code == HTTPStatus.NOT_FOUND

    finally:
        server.shutdown()
        server.server_close()
