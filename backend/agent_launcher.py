from __future__ import annotations

import argparse
import multiprocessing
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

import uvicorn

from app.config import application_home
from app.main import app


def find_available_port(preferred: int) -> int:
    if preferred == 0:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("找不到可用的本地端口")


def open_browser_when_ready(url: str) -> None:
    health_url = f"{url}/api/health"
    for _ in range(120):
        try:
            with urllib.request.urlopen(health_url, timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.25)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Agent Chat desktop launcher")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    return parser.parse_args()


def main() -> None:
    multiprocessing.freeze_support()
    args = parse_args()
    port = find_available_port(args.port)
    browser_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    url = f"http://{browser_host}:{port}"

    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleTitleW(f"Agent Chat - {url}")
        except (AttributeError, OSError):
            pass

    data_home = application_home()
    print()
    print("  Agent Chat")
    print(f"  服务地址: {url}")
    print(f"  数据目录: {data_home}")
    print("  关闭此窗口即可停止服务。")
    print()

    if not args.no_browser:
        threading.Thread(
            target=open_browser_when_ready,
            args=(url,),
            daemon=True,
        ).start()

    try:
        uvicorn.run(
            app,
            host=args.host,
            port=port,
            log_level="info",
            access_log=True,
        )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

