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
from typing import Optional, Tuple, Any

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
        """解析 Range 标头并以 206 Partial Content 回应数据切片"""
        match = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if not match:
            self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            return

        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else file_size - 1

        if start >= file_size or end >= file_size or start > end:
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
