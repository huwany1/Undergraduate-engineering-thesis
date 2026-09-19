# -*- coding: utf-8 -*-
"""
Web 交互演示系统自动化测试套件 (Web Demo Tests)
覆盖:
1. DemoService 业务逻辑与数据资产提取;
2. WebDemoRequestHandler REST 接口契约;
3. 静态文件与 HTTP 206 视频流式切片分发;
4. 异常路径与越界安全防御.
"""

import json
import threading
import urllib.request
import urllib.error
from pathlib import Path
import pytest

from web_demo.service import DemoService
from web_demo.server import run_server


@pytest.fixture(scope="module")
def demo_service():
    return DemoService()


@pytest.fixture(scope="module")
def web_server():
    """启动测试专用多线程 HTTP 服务"""
    # 动态分配可用测试端口
    server = run_server(port=0, host="127.0.0.1")
    actual_port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{actual_port}"
    yield base_url

    server.shutdown()
    server.server_close()


# =========================================================================
# 1. 业务适配层 (DemoService) 测试
# =========================================================================

def test_demo_service_status(demo_service):
    status = demo_service.get_status()
    assert status["service"] == "squat-motion-assessment-web-demo"
    assert status["status"] == "ONLINE"
    assert status["baseline_id"] == "P0-SQUAT-SIDE-OFFLINE-v1.0"
    assert status["total_golden_cases"] == 5


def test_demo_service_cases(demo_service):
    cases = demo_service.get_cases()
    assert len(cases) == 5
    case_ids = [c["case_id"] for c in cases]
    assert "TC_01_PERFECT_SQUAT" in case_ids
    assert "TC_02_SHALLOW_SQUAT" in case_ids
    assert "TC_03_EXCESSIVE_LEAN" in case_ids
    assert "TC_04_DUAL_DEFECT" in case_ids
    assert "TC_05_OUT_OF_FRAME" in case_ids

    # 验证视频产物标记
    for c in cases:
        assert c["has_video"] is True
        assert c["video_url"].startswith("/api/media/replays/")


def test_demo_service_case_detail_success(demo_service):
    detail = demo_service.get_case_detail("TC_01_PERFECT_SQUAT")
    assert detail is not None
    assert detail["case_id"] == "TC_01_PERFECT_SQUAT"
    assert detail["actual_status"] == "ACCEPTABLE"
    assert detail["actual_count"] == 1
    assert detail["measured_min_knee_angle"] > 0
    assert detail["measured_max_torso_angle"] > 0

    # 验证时序数据流
    telemetry = detail["telemetry"]
    assert len(telemetry) > 0
    assert "knee_angle" in telemetry[0]
    assert "torso_angle" in telemetry[0]
    assert "fsm_state" in telemetry[0]

    # 验证关键特征帧
    keyframes = detail["keyframes"]
    assert len(keyframes) >= 3
    for kf in keyframes:
        assert kf["image_url"].startswith("/api/media/screenshots/")


def test_demo_service_case_detail_not_found(demo_service):
    detail = demo_service.get_case_detail("NON_EXISTENT_CASE")
    assert detail is None


def test_demo_service_validation_report(demo_service):
    report = demo_service.get_validation_report()
    assert "manifest" in report
    assert "summary_markdown" in report
    assert "metrics_csv" in report
    assert len(report["metrics_csv"]) == 5
    assert report["manifest"]["concordance_rate"] == 1.0


# =========================================================================
# 2. HTTP 服务端与 REST API 测试
# =========================================================================

def test_api_status_endpoint(web_server):
    url = f"{web_server}/api/status"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["service"] == "squat-motion-assessment-web-demo"
        assert data["status"] == "ONLINE"


def test_api_cases_endpoint(web_server):
    url = f"{web_server}/api/cases"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert isinstance(data, list)
        assert len(data) == 5


def test_api_case_detail_endpoint(web_server):
    url = f"{web_server}/api/case/TC_02_SHALLOW_SQUAT"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["case_id"] == "TC_02_SHALLOW_SQUAT"
        assert data["actual_status"] == "NEEDS_IMPROVEMENT"
        assert "下蹲深度不足" in data["summary_feedback"]


def test_api_case_detail_404(web_server):
    url = f"{web_server}/api/case/INVALID_ID"
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(url)
    assert exc_info.value.code == 404


def test_api_validation_report_endpoint(web_server):
    url = f"{web_server}/api/reports/validation"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["manifest"]["total_cases"] == 5


# =========================================================================
# 3. 静态资源与流式媒体传输测试
# =========================================================================

def test_static_index_html(web_server):
    url = f"{web_server}/"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        assert "text/html" in resp.headers.get("Content-Type", "")
        content = resp.read().decode("utf-8")
        assert "深蹲动作质量辅助评估" in content


def test_static_css_and_js(web_server):
    # CSS
    css_url = f"{web_server}/static/css/style.css"
    with urllib.request.urlopen(css_url) as resp:
        assert resp.status == 200
        assert "text/css" in resp.headers.get("Content-Type", "")

    # JS
    js_url = f"{web_server}/static/js/chart.js"
    with urllib.request.urlopen(js_url) as resp:
        assert resp.status == 200
        content = resp.read().decode("utf-8")
        assert "TelemetryChart" in content


def test_media_video_streaming_and_range_requests(web_server):
    video_url = f"{web_server}/api/media/replays/TC_01_PERFECT_SQUAT_annotated.mp4"

    # 1. 普通全量请求
    req_full = urllib.request.Request(video_url)
    with urllib.request.urlopen(req_full) as resp:
        assert resp.status == 200
        assert resp.headers.get("Content-Type") == "video/mp4"
        assert resp.headers.get("Accept-Ranges") == "bytes"
        total_size = int(resp.headers.get("Content-Length"))
        assert total_size > 500000

    # 2. HTTP 206 Partial Content (分段 Range 请求)
    req_range = urllib.request.Request(video_url, headers={"Range": "bytes=0-1023"})
    with urllib.request.urlopen(req_range) as resp:
        assert resp.status == 206
        assert resp.headers.get("Content-Type") == "video/mp4"
        assert resp.headers.get("Content-Range") == f"bytes 0-1023/{total_size}"
        assert int(resp.headers.get("Content-Length")) == 1024
        data = resp.read()
        assert len(data) == 1024

    # 3. HTTP 206 Suffix Range 请求 (bytes=-suffix，用于读取 MP4 尾部 moov 索引元数据)
    req_suffix = urllib.request.Request(video_url, headers={"Range": "bytes=-512"})
    with urllib.request.urlopen(req_suffix) as resp:
        assert resp.status == 206
        assert resp.headers.get("Content-Type") == "video/mp4"
        expected_start = total_size - 512
        expected_end = total_size - 1
        assert resp.headers.get("Content-Range") == f"bytes {expected_start}-{expected_end}/{total_size}"
        assert int(resp.headers.get("Content-Length")) == 512
        data_suffix = resp.read()
        assert len(data_suffix) == 512


def test_media_screenshot_delivery(web_server):
    img_url = f"{web_server}/api/media/screenshots/TC_01_PERFECT_SQUAT_bottom_inflection_f037.png"
    with urllib.request.urlopen(img_url) as resp:
        assert resp.status == 200
        assert resp.headers.get("Content-Type") == "image/png"
        assert int(resp.headers.get("Content-Length")) > 10000


def test_security_path_traversal_blocked(web_server):
    """验证越界路径访问防御"""
    bad_url = f"{web_server}/static/../../pyproject.toml"
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(bad_url)
    assert exc_info.value.code in (403, 404)
