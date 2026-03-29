"""
Launch Magic Sisi IDE UI in a native window (pywebview) and start uvicorn if needed.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import webview

PORT = int(os.environ.get("MAGIC_PORT", "8787"))
URL = f"http://127.0.0.1:{PORT}/sisi"
PROJECT_ROOT = Path(__file__).resolve().parent


def _venv_python() -> Path:
    mac = PROJECT_ROOT / ".venv" / "bin" / "python3"
    if mac.is_file():
        return mac
    win = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    if win.is_file():
        return win
    return Path(sys.executable)


def is_server_running() -> bool:
    try:
        return urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1).getcode() == 200
    except Exception:
        return False


def start_server() -> subprocess.Popen:
    py = _venv_python()
    print("Starting Magic API for Sisi…")
    env = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT), "MAGIC_PORT": str(PORT)}
    proc = subprocess.Popen(
        [
            str(py),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
        ],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    for _ in range(60):
        if is_server_running():
            return proc
        if proc.poll() is not None:
            err = b""
            if proc.stderr:
                err = proc.stderr.read() or b""
            print("Server exited early:", err.decode("utf-8", errors="replace")[:800])
            sys.exit(1)
        time.sleep(0.5)
    print(f"Timed out waiting for http://127.0.0.1:{PORT}/health — is the port free?")
    proc.terminate()
    sys.exit(1)


def main() -> None:
    server_proc: subprocess.Popen | None = None
    if not is_server_running():
        server_proc = start_server()

    print("Opening Magic Sisi…")
    webview.create_window(
        "Magic Sisi IDE",
        URL,
        width=1350,
        height=900,
        text_select=True,
        zoomable=True,
    )
    webview.start(private_mode=False)

    if server_proc is not None:
        print("Stopping API server…")
        server_proc.terminate()


if __name__ == "__main__":
    main()
