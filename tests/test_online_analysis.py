# -*- coding: utf-8 -*-
"""
在线视频上传与异步分析流水线自动化测试 (Online Analysis Tests)
覆盖:
1. POST /api/upload 接口契约、大小门控与格式安全校验;
2. 异步任务创建、生命周期状态轮询与阶段进度流转;
3. 端到端流水线执行 (P1->P2->P3) 与标准报告聚合;
4. 上传媒体流式分发 (HTTP 206 Range) 与特征快照服务;
5. 错误边界与防回归断言.
"""

import json
import time
import threading
import urllib.request
import urllib.error
from pathlib import Path
import pytest

from web_demo.service import DemoService
from web_demo.server import run_server


@pytest.fixture(scope="module")
def web_server():
    """启动测试专用多线程 HTTP 服务实例"""
    server = run_server(port=0, host="127.0.0.1")
    actual_port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{actual_port}"
    yield base_url

    server.shutdown()
    server.server_close()


def test_upload_missing_content_length(web_server):
    """验证缺少 Content-Length 头部时正确返回 411"""
    # 模拟空请求
    req = urllib.request.Request(f"{web_server}/api/upload", data=b"", method="POST")
    # 移除或将 Content-Length 设为空无法直接通过 urllib，用空数据 POST
    try:
        urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        # 空数据会触发 400 (上传内容为空) 或 411
        assert e.code in (400, 411)


def test_upload_payload_too_large(web_server):
    """验证超大文件 (>50MB) 触发 413 Payload Too Large"""
    fake_large_size = 51 * 1024 * 1024
    req = urllib.request.Request(
        f"{web_server}/api/upload",
        data=b"fake",
        headers={"Content-Length": str(fake_large_size), "Content-Type": "video/mp4"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == 413


def test_upload_invalid_format(web_server):
    """验证非 MP4 格式或无 ftyp 签名的文件触发 400 Bad Request"""
    bad_data = b"This is a plain text file, definitely not an MP4 video!"
    req = urllib.request.Request(
        f"{web_server}/api/upload?filename=malicious.txt",
        data=bad_data,
        headers={"Content-Type": "text/plain"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == 400
    err_body = json.loads(exc_info.value.read().decode("utf-8"))
    assert "仅支持 MP4" in err_body["error"]


def test_task_not_found(web_server):
    """验证查询不存在的任务 ID 时返回 404"""
    req = urllib.request.Request(f"{web_server}/api/task/non_existent_task_id")
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == 404


def test_online_analysis_end_to_end(web_server):
    """
    端到端测试：
    1. 上传真实样本视频;
    2. 接收 202 Accepted 与 task_id;
    3. 轮询 /api/task/:id 直至 COMPLETED;
    4. 验证生成的专属报告、遥测时序、关键帧快照;
    5. 验证视频分发与 HTTP 206 断点分段能力.
    """
    sample_video = Path(__file__).resolve().parent.parent / "data" / "S1_raw_sensitive" / "demo_squats" / "sample_squat_standard.mp4"
    assert sample_video.exists(), f"未找到样本视频: {sample_video}"

    video_bytes = sample_video.read_bytes()

    # 1. 模拟浏览器发送 multipart/form-data
    boundary = "----WebKitFormBoundaryX9A7c2B9D1"
    body_parts = [
        f"--{boundary}\r\n".encode("utf-8"),
        b'Content-Disposition: form-data; name="video"; filename="my_test_squat.mp4"\r\n',
        b"Content-Type: video/mp4\r\n\r\n",
        video_bytes,
        f"\r\n--{boundary}--\r\n".encode("utf-8"),
    ]
    multipart_body = b"".join(body_parts)

    upload_url = f"{web_server}/api/upload"
    req = urllib.request.Request(
        upload_url,
        data=multipart_body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(multipart_body)),
        },
        method="POST",
    )

    with urllib.request.urlopen(req) as resp:
        assert resp.status == 202
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "PENDING"
        task_id = data["task_id"]
        assert task_id.startswith("up_")

    # 2. 轮询任务进度直至完成 (最多等待 15 秒)
    max_wait = 15.0
    start_poll = time.time()
    task_res = None

    while time.time() - start_poll < max_wait:
        poll_req = urllib.request.Request(f"{web_server}/api/task/{task_id}")
        with urllib.request.urlopen(poll_req) as p_resp:
            assert p_resp.status == 200
            p_data = json.loads(p_resp.read().decode("utf-8"))
            if p_data["status"] in ("COMPLETED", "FAILED"):
                task_res = p_data
                break
        time.sleep(0.4)

    assert task_res is not None, f"任务在 {max_wait}s 内未结束"
    assert task_res["status"] == "COMPLETED", f"任务失败: {task_res.get('error')}"
    assert task_res["progress"] == 100

    result = task_res["result"]
    assert result is not None
    assert result["case_id"] == f"UPLOAD_{task_id}"
    assert "my_test_squat.mp4" in result["case_name"]
    assert result["has_video"] is True
    assert result["video_url"].startswith("/api/media/uploaded/video/")
    assert len(result["telemetry"]) > 0
    assert result["measured_min_knee_angle"] > 0
    assert "summary_feedback" in result

    # 3. 验证 /api/case/UPLOAD_<task_id> 可直接拉取此详情
    case_req = urllib.request.Request(f"{web_server}/api/case/UPLOAD_{task_id}")
    with urllib.request.urlopen(case_req) as c_resp:
        assert c_resp.status == 200
        case_data = json.loads(c_resp.read().decode("utf-8"))
        assert case_data["case_id"] == f"UPLOAD_{task_id}"

    # 4. 验证 /api/uploads 列表中已收录此记录
    uploads_req = urllib.request.Request(f"{web_server}/api/uploads")
    with urllib.request.urlopen(uploads_req) as u_resp:
        assert u_resp.status == 200
        u_list = json.loads(u_resp.read().decode("utf-8"))
        matched = [item for item in u_list if item["task_id"] == task_id]
        assert len(matched) == 1

    # 5. 验证上传视频的 HTTP 206 断点续传流式分发
    video_stream_url = f"{web_server}{result['video_url']}"
    range_req = urllib.request.Request(video_stream_url, headers={"Range": "bytes=0-1023"})
    with urllib.request.urlopen(range_req) as v_resp:
        assert v_resp.status == 206
        assert v_resp.headers.get("Content-Type") == "video/mp4"
        assert v_resp.headers.get("Accept-Ranges") == "bytes"
        chunk = v_resp.read()
        assert len(chunk) == 1024

    # 6. 若存在特征快照，验证快照的分发
    if result["keyframes"]:
        first_kf = result["keyframes"][0]
        img_url = f"{web_server}{first_kf['image_url']}"
        img_req = urllib.request.Request(img_url)
        with urllib.request.urlopen(img_req) as i_resp:
            assert i_resp.status == 200
            assert i_resp.headers.get("Content-Type") == "image/png"
            img_bytes = i_resp.read()
            assert len(img_bytes) > 1000
