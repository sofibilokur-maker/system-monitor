import os
import sys
import time
import threading
import urllib.request

import uvicorn
import webview

import agent                      # твій agent.py
from server import app            # твій server.py


def resource_path(*parts):

    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


DASHBOARD_FILE = resource_path("dashboard", "dashboard.html")
SERVER_URL = "http://127.0.0.1:8000"

server = None


def wait_for_server(timeout=30):
    print("[LAUNCHER] Waiting for server...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(SERVER_URL + "/health", timeout=1):
                print("[LAUNCHER] Server is ready.")
                return True
        except Exception:
            time.sleep(0.5)
    print("[LAUNCHER] Server did not start.")
    return False


def start_server():
    global server
    print("[LAUNCHER] Starting FastAPI server...")
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=8000,
        log_config=None,
    )
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()


def start_agent():
    print("[LAUNCHER] Starting monitoring agent...")
    threading.Thread(target=agent.main, daemon=True).start()


def stop_processes():
    print("[LAUNCHER] Closing System Monitor...")
    if server is not None:
        server.should_exit = True
    # потоки daemon: завершаться разом із програмою


def main():
    print("=" * 50)
    print("          SYSTEM MONITOR")
    print("=" * 50)

    if not os.path.exists(DASHBOARD_FILE):
        print("[ERROR] Dashboard not found:", DASHBOARD_FILE)
        input("\nPress Enter to exit...")
        return

    start_server()

    if not wait_for_server():
        stop_processes()
        input("\nPress Enter to exit...")
        return

    start_agent()

    print("[LAUNCHER] Opening Dashboard...")
    dashboard_url = "file:///" + DASHBOARD_FILE.replace("\\", "/")

    webview.create_window(
        "System Monitor",
        dashboard_url,
        width=1450,
        height=900,
        min_size=(1000, 650),
        resizable=True,
    )

    try:
        webview.start()
    finally:
        stop_processes()


if __name__ == "__main__":
    main()