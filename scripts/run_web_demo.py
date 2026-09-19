# -*- coding: utf-8 -*-
"""
深蹲动作质量辅助评估 Web 交互系统启动脚本
执行命令: uv run python scripts/run_web_demo.py
"""

import sys
import argparse
import webbrowser
import socket
from pathlib import Path

# 控制台编码安全配置
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 确保项目根目录在 sys.path 中
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from web_demo.server import run_server
from web_demo.llm_coach import load_dotenv_fallback

# 启动前自动载入本地 .env 文件（若存在）
load_dotenv_fallback(REPO_ROOT)


def find_available_port(start_port: int = 8080, host: str = "127.0.0.1", max_attempts: int = 20) -> int:
    """自动探测可用网络端口"""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((host, port)) != 0:
                return port
    return start_port


def main():
    parser = argparse.ArgumentParser(description="深蹲动作质量辅助评估 Web 交互演示系统")
    parser.add_argument("--host", default="127.0.0.1", help="绑定监听的主机地址 (默认: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="监听端口 (默认: 8080)")
    parser.add_argument("--open", action="store_true", help="启动后自动在系统默认浏览器中打开页面")
    args = parser.parse_args()

    actual_port = find_available_port(args.port, args.host)

    server = run_server(port=actual_port, host=args.host, repo_root=REPO_ROOT)
    url = f"http://{args.host}:{actual_port}/"

    print("=" * 72)
    print("  [DEMO] 深蹲动作质量辅助评估 Web 交互演示系统已就绪")
    print("=" * 72)
    print(f"  服务访问地址: {url}")
    print(f"  工程基线口径: P0-SQUAT-SIDE-OFFLINE-v1.0")
    print(f"  黄金验证资产: 5 大典型场景 (reports/validation_package/)")
    print("  按 Ctrl + C 可优雅关闭演示服务")
    print("=" * 72)

    if args.open:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] 正在关闭演示服务...")
        server.shutdown()
        server.server_close()
        print("[SUCCESS] 演示服务已安全退出。")


if __name__ == "__main__":
    main()
