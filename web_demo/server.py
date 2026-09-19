# -*- coding: utf-8 -*-
"""
轻量级 Web 服务器与 REST 路由分发器 (Web Demo Server)
依据: ThreadingHTTPServer + 原生 RESTful API + HTTP 206 视频切片流式分发
"""

import os
import sys
import json
import mimetypes
import re
from pathlib import Path
from http import HTTPStatus
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from typing import Optional, Tuple, Any, Dict, List

from .service import DemoService


class WebDemoRequestHandler(SimpleHTTPRequestHandler):
    """自定义 REST API 与高质感静态资源请求处理器"""

    service: DemoService = None  # 类属性注入
    static_dir: Path = None       # 静态资源根目录
    repo_root: Path = None        # 项目根目录

    def end_headers(self):
        # 统一添加 CORS 与防缓存头（静态媒体除外）
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Range")
        super().end_headers()

    def do_OPTIONS(self):
        """处理预检请求"""
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_POST(self):
        """处理 HTTP POST 请求 (如视频上传、在线分析与实时摄像头帧交互)"""
        path = self.path.split("?")[0]
        if path in ("/api/upload", "/api/analyze"):
            self._handle_api_upload()
            return
        elif path == "/api/live/session/start":
            self._handle_live_start()
            return
        elif path.startswith("/api/live/session/") and path.endswith("/frame"):
            self._handle_live_frame()
            return
        elif path.startswith("/api/live/session/") and path.endswith("/stop"):
            self._handle_live_stop()
            return
        elif path == "/api/llm/config":
            self._handle_llm_config_post()
            return
        elif path == "/api/llm/test":
            self._handle_llm_test_post()
            return
        elif path == "/api/llm/feedback":
            self._handle_llm_feedback_post()
            return
        elif path == "/api/llm/chat":
            self._handle_llm_chat_post()
            return
        self._send_json({"error": f"Unknown POST endpoint: {path}"}, status=HTTPStatus.NOT_FOUND)

    def _handle_live_start(self):
        """启动新实时摄像头会话"""
        try:
            data = self.service.start_live_session()
            self._send_json(data, status=HTTPStatus.CREATED)
        except Exception as ex:
            self._send_json({"error": f"Failed to start live session: {str(ex)}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_live_frame(self):
        """处理摄像头推流单帧并即时返回骨架与生物力学指标"""
        try:
            parts = self.path.split("?")[0].split("/")
            # 预期格式: ["", "api", "live", "session", "<session_id>", "frame"]
            if len(parts) < 6:
                self._send_json({"error": "Invalid live frame path"}, status=HTTPStatus.BAD_REQUEST)
                return
            session_id = parts[4]

            content_length_str = self.headers.get("Content-Length")
            if not content_length_str:
                self._send_json({"error": "Missing Content-Length header"}, status=HTTPStatus.LENGTH_REQUIRED)
                return

            try:
                content_length = int(content_length_str)
            except ValueError:
                self._send_json({"error": "Invalid Content-Length header"}, status=HTTPStatus.BAD_REQUEST)
                return

            if content_length > 5 * 1024 * 1024:
                self._send_json({"error": "Frame payload too large"}, status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                return

            frame_bytes = self.rfile.read(content_length)
            client_ts_header = self.headers.get("X-Client-Timestamp")
            client_ts_ms = int(client_ts_header) if (client_ts_header and client_ts_header.isdigit()) else None

            res = self.service.process_live_frame(session_id, frame_bytes, client_ts_ms)
            if res is None:
                self._send_json({"error": f"Live session not found: {session_id}"}, status=HTTPStatus.NOT_FOUND)
                return

            self._send_json(res, status=HTTPStatus.OK)
        except Exception as ex:
            self._send_json({"error": f"Live frame inference failed: {str(ex)}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_live_stop(self):
        """关闭实时摄像头会话并获取总结"""
        try:
            parts = self.path.split("?")[0].split("/")
            if len(parts) < 6:
                self._send_json({"error": "Invalid live stop path"}, status=HTTPStatus.BAD_REQUEST)
                return
            session_id = parts[4]

            summary = self.service.stop_live_session(session_id)
            if summary is None:
                self._send_json({"error": f"Live session not found: {session_id}"}, status=HTTPStatus.NOT_FOUND)
                return

            self._send_json(summary, status=HTTPStatus.OK)
        except Exception as ex:
            self._send_json({"error": f"Failed to stop live session: {str(ex)}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _read_json_body(self) -> Dict[str, Any]:
        """读取并解析 JSON 请求体"""
        content_length_str = self.headers.get("Content-Length")
        if not content_length_str:
            return {}
        try:
            content_length = int(content_length_str)
        except ValueError:
            return {}
        if content_length <= 0 or content_length > 10 * 1024 * 1024:
            return {}
        raw_bytes = self.rfile.read(content_length)
        try:
            return json.loads(raw_bytes.decode("utf-8"))
        except Exception:
            return {}

    def _handle_llm_config_post(self):
        """保存大模型 API Key 与端点配置"""
        try:
            body = self._read_json_body()
            api_key = body.get("api_key")
            base_url = body.get("base_url")
            model = body.get("model")
            res = self.service.update_llm_config(api_key=api_key, base_url=base_url, model=model)
            self._send_json(res, status=HTTPStatus.OK)
        except Exception as ex:
            self._send_json({"error": f"Failed to update LLM config: {str(ex)}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_llm_test_post(self):
        """测试 DeepSeek API 连通性与往返延迟"""
        try:
            body = self._read_json_body()
            api_key = body.get("api_key")
            base_url = body.get("base_url")
            model = body.get("model")
            res = self.service.test_llm_connection(api_key=api_key, base_url=base_url, model=model)
            self._send_json(res, status=HTTPStatus.OK)
        except Exception as ex:
            self._send_json({"error": f"Failed to test LLM connection: {str(ex)}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_llm_feedback_post(self):
        """请求生成动作报告的 AI 深度指导"""
        try:
            body = self._read_json_body()
            case_id = body.get("case_id")
            report_data = body.get("report_data")
            prompt_override = body.get("prompt_override")
            res = self.service.generate_llm_feedback(case_id=case_id, report_data=report_data, prompt_override=prompt_override)
            self._send_json(res, status=HTTPStatus.OK)
        except Exception as ex:
            self._send_json({"error": f"Failed to generate LLM feedback: {str(ex)}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_llm_chat_post(self):
        """多轮问答对话"""
        try:
            body = self._read_json_body()
            messages = body.get("messages", [])
            case_id = body.get("case_id")
            report_data = body.get("report_data")
            if not isinstance(messages, list):
                self._send_json({"error": "messages must be a list"}, status=HTTPStatus.BAD_REQUEST)
                return
            res = self.service.chat_with_llm(messages=messages, case_id=case_id, report_data=report_data)
            self._send_json(res, status=HTTPStatus.OK)
        except Exception as ex:
            self._send_json({"error": f"Failed to chat with LLM: {str(ex)}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)



    def _handle_api_upload(self):
        """处理视频上传并启动后台分析任务"""
        try:
            content_length_str = self.headers.get("Content-Length")
            if not content_length_str:
                self._send_json({"error": "Missing Content-Length header"}, status=HTTPStatus.LENGTH_REQUIRED)
                return

            try:
                content_length = int(content_length_str)
            except ValueError:
                self._send_json({"error": "Invalid Content-Length header"}, status=HTTPStatus.BAD_REQUEST)
                return

            # 文件大小硬限 50MB
            if content_length > 50 * 1024 * 1024:
                self._send_json(
                    {"error": f"Payload too large (size: {content_length / 1024 / 1024:.1f}MB, limit: 50MB)"},
                    status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                )
                return

            body_bytes = self.rfile.read(content_length)
            content_type = self.headers.get("Content-Type", "")

            # 解析查询参数或头部中的文件名
            import urllib.parse
            from .analyzer import parse_upload_payload
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            query_filename = query.get("filename", [None])[0] or self.headers.get("X-Filename")

            filename, file_bytes = parse_upload_payload(body_bytes, content_type, query_filename)

            # 校验并提交异步任务
            task_id = self.service.submit_video_analysis(file_bytes, filename)
            self._send_json(
                {
                    "task_id": task_id,
                    "status": "PENDING",
                    "filename": filename,
                    "message": "视频已成功接收，在线分析任务已提交",
                },
                status=HTTPStatus.ACCEPTED,
            )
        except ValueError as ve:
            self._send_json({"error": str(ve)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as ex:
            self._send_json({"error": f"Upload failed: {str(ex)}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_GET(self):
        """处理 HTTP GET 请求"""
        path = self.path.split("?")[0]

        # 1. REST API 路由
        if path.startswith("/api/"):
            self._handle_api_get(path)
            return

        # 2. 媒体流式分发 (/api/media/...)
        if path.startswith("/media/"):
            # 兼容 /media/ 路径
            self._handle_media_get(path.replace("/media/", "/api/media/"))
            return

        # 3. 根路径重定向到前端单页应用
        if path in ("", "/"):
            self._serve_file(self.static_dir / "index.html", "text/html; charset=utf-8")
            return

        # 4. 静态资源路由 (/static/...)
        if path.startswith("/static/"):
            relative_subpath = path[len("/static/"):]
            file_path = (self.static_dir / relative_subpath).resolve()
            # 路径越界安全防护
            if not str(file_path).startswith(str(self.static_dir.resolve())):
                self._send_json({"error": "Forbidden: Path traversal blocked"}, status=HTTPStatus.FORBIDDEN)
                return
            if file_path.is_file():
                content_type, _ = mimetypes.guess_type(str(file_path))
                self._serve_file(file_path, content_type or "application/octet-stream")
                return
            self._send_json({"error": f"Static asset not found: {relative_subpath}"}, status=HTTPStatus.NOT_FOUND)
            return

        # 5. 回退到直接匹配 static 目录下的文件
        candidate = (self.static_dir / path.lstrip("/")).resolve()
        if candidate.is_file() and str(candidate).startswith(str(self.static_dir.resolve())):
            content_type, _ = mimetypes.guess_type(str(candidate))
            self._serve_file(candidate, content_type or "application/octet-stream")
            return

        self._send_json({"error": f"Not Found: {path}"}, status=HTTPStatus.NOT_FOUND)

    def _handle_api_get(self, path: str):
        """处理 REST API GET 接口"""
        try:
            if path == "/api/status":
                data = self.service.get_status()
                self._send_json(data)
            elif path == "/api/cases":
                data = self.service.get_cases()
                self._send_json(data)
            elif path.startswith("/api/case/"):
                case_id = path.split("/api/case/")[1].strip("/")
                data = self.service.get_case_detail(case_id)
                if data is None:
                    self._send_json({"error": f"Case not found: {case_id}"}, status=HTTPStatus.NOT_FOUND)
                else:
                    self._send_json(data)
            elif path == "/api/reports/validation":
                data = self.service.get_validation_report()
                self._send_json(data)
            elif path == "/api/dataset_demos":
                data = self.service.get_dataset_demos()
                self._send_json(data)
            elif path.startswith("/api/dataset_demo/"):
                demo_id = path.split("/api/dataset_demo/")[1].strip("/")
                data = self.service.get_dataset_demo_detail(demo_id)
                if data is None:
                    self._send_json({"error": f"Dataset demo not found: {demo_id}"}, status=HTTPStatus.NOT_FOUND)
                else:
                    self._send_json(data)
            elif path.startswith("/api/task/"):
                task_id = path.split("/api/task/")[1].strip("/")
                task_data = self.service.get_analysis_task(task_id)
                if task_data is None:
                    self._send_json({"error": f"Task not found: {task_id}"}, status=HTTPStatus.NOT_FOUND)
                else:
                    self._send_json(task_data)
            elif path == "/api/uploads":
                data = self.service.list_uploaded_cases()
                self._send_json(data)
            elif path == "/api/llm/config":
                data = self.service.get_llm_config()
                self._send_json(data)
            elif path.startswith("/api/live/session/"):
                session_id = path.split("/api/live/session/")[1].strip("/")
                data = self.service.get_live_session_status(session_id)
                if data is None:
                    self._send_json({"error": f"Live session not found: {session_id}"}, status=HTTPStatus.NOT_FOUND)
                else:
                    self._send_json(data)
            elif path.startswith("/api/media/"):
                self._handle_media_get(path)
            else:
                self._send_json({"error": f"Unknown API endpoint: {path}"}, status=HTTPStatus.NOT_FOUND)
        except Exception as ex:
            self._send_json({"error": f"Server internal error: {str(ex)}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_media_get(self, path: str):
        """
        媒体资源流式分发，支持 HTTP 206 Range 分段请求
        特别针对 HTML5 <video> 标签在进度条拖拽与时间寻址 (Seek) 场景
        """
        subpath = path.replace("/api/media/", "")
        if subpath.startswith("dataset_demo/"):
            media_root = self.repo_root / "reports" / "dataset_demo"
            subpath = subpath[len("dataset_demo/"):]
            file_path = (media_root / subpath).resolve()
        elif subpath.startswith("uploaded/"):
            # 用户上传视频与生成截图
            sub = subpath[len("uploaded/"):]
            if sub.startswith("video/"):
                media_root = self.repo_root / "reports" / "uploaded_demo" / "uploads"
                file_path = (media_root / sub[len("video/"):]).resolve()
            elif sub.startswith("screenshot/"):
                media_root = self.repo_root / "reports" / "uploaded_demo" / "screenshots"
                file_path = (media_root / sub[len("screenshot/"):]).resolve()
            else:
                media_root = self.repo_root / "reports" / "uploaded_demo"
                file_path = (media_root / sub).resolve()
        else:
            media_root = self.repo_root / "reports" / "validation_package"
            file_path = (media_root / subpath).resolve()

        # 安全防御：禁止逃逸出指定媒体根目录
        if not str(file_path).startswith(str(media_root.resolve())):
            self._send_json({"error": "Forbidden"}, status=HTTPStatus.FORBIDDEN)
            return

        if not file_path.is_file():
            self._send_json({"error": f"Media file not found: {subpath}"}, status=HTTPStatus.NOT_FOUND)
            return

        content_type, _ = mimetypes.guess_type(str(file_path))
        if str(file_path).endswith(".mp4"):
            content_type = "video/mp4"
        elif str(file_path).endswith(".png"):
            content_type = "image/png"

        file_size = file_path.stat().st_size
        range_header = self.headers.get("Range")

        if range_header:
            self._serve_range(file_path, file_size, content_type or "application/octet-stream", range_header)
        else:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type or "application/octet-stream")
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            with open(file_path, "rb") as f:
                self.copyfile(f, self.wfile)

    def _serve_range(self, file_path: Path, file_size: int, content_type: str, range_header: str):
        """
        解析 HTTP Range 标头并以 206 Partial Content 回应数据切片。
        全面兼容 RFC 7233 标准：
        1. 标准范围: bytes=start-end (例如 bytes=0-1024)
        2. 开口范围: bytes=start- (例如 bytes=1024-)
        3. 后缀范围: bytes=-suffix (例如 bytes=-4096，现代浏览器读取 MP4 尾部 moov 索引的关键)
        """
        range_str = range_header.strip()
        suffix_match = re.match(r"^bytes=-(\d+)$", range_str)
        standard_match = re.match(r"^bytes=(\d+)-(\d*)$", range_str)

        if suffix_match:
            suffix_len = int(suffix_match.group(1))
            if suffix_len <= 0:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{file_size}")
                self.end_headers()
                return
            start = max(0, file_size - suffix_len)
            end = file_size - 1
        elif standard_match:
            start = int(standard_match.group(1))
            end_str = standard_match.group(2)
            end = int(end_str) if end_str else file_size - 1
            if start >= file_size or end >= file_size or start > end:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{file_size}")
                self.end_headers()
                return
        else:
            self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            self.send_header("Content-Range", f"bytes */{file_size}")
            self.end_headers()
            return

        chunk_size = end - start + 1
        self.send_response(HTTPStatus.PARTIAL_CONTENT)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Content-Length", str(chunk_size))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

        with open(file_path, "rb") as f:
            f.seek(start)
            bytes_left = chunk_size
            buf_size = 64 * 1024
            while bytes_left > 0:
                read_amount = min(bytes_left, buf_size)
                chunk = f.read(read_amount)
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (ConnectionResetError, BrokenPipeError):
                    break
                bytes_left -= len(chunk)

    def _serve_file(self, file_path: Path, content_type: str):
        """分发静态常规文件"""
        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self._send_json({"error": f"Failed to read file: {str(e)}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _send_json(self, data: Any, status: HTTPStatus = HTTPStatus.OK):
        """以标准 JSON 结构响应"""
        payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def run_server(
    port: int = 8080,
    host: str = "127.0.0.1",
    repo_root: Optional[Path] = None,
) -> ThreadingHTTPServer:
    """初始化并构建 Web 服务器实例"""
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parent.parent
    static_dir = Path(__file__).resolve().parent / "static"

    service = DemoService(repo_root=root)

    # 注入类属性
    WebDemoRequestHandler.service = service
    WebDemoRequestHandler.static_dir = static_dir
    WebDemoRequestHandler.repo_root = root

    server = ThreadingHTTPServer((host, port), WebDemoRequestHandler)
    return server
