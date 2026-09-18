# -*- coding: utf-8 -*-
"""
深蹲动作质量辅助评估 Web 交互演示系统 (Web Demo Package)
提供轻量级 HTTP 服务与高质感交互界面
"""

__version__ = "0.1.0"
__all__ = ["run_server", "DemoService"]

from .server import run_server
from .service import DemoService
