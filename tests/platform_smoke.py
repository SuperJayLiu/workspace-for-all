#!/usr/bin/env python3
"""Cross-platform startup smoke test that never writes to the live checkout."""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent.parent


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def fetch(url, attempts=40, proc=None, log_path=None):
    last = None
    for _ in range(attempts):
        if proc is not None and proc.poll() is not None:
            details = ""
            if log_path is not None and log_path.exists():
                details = log_path.read_text(encoding="utf-8", errors="replace").strip()
            raise RuntimeError(
                f"service exited before becoming ready (exit {proc.returncode})"
                + (f":\n{details}" if details else "")
            )
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                return response.status, response.read()
        except Exception as exc:  # service may still be starting
            last = exc
            time.sleep(0.25)
    raise RuntimeError(f"service did not become ready: {last}")


def ignored(_directory, names):
    blocked = {".git", "local", "attachments", "node_modules", "__pycache__"}
    return [name for name in names if name in blocked or name.endswith((".zip", ".pyc"))]


def main():
    with tempfile.TemporaryDirectory(prefix="scholar-platform-smoke-") as temporary:
        root = Path(temporary) / "workspace"
        shutil.copytree(SOURCE_ROOT, root, ignore=ignored)
        (root / "local").mkdir(exist_ok=True)
        port = free_port()
        log_path = Path(temporary) / "server.log"
        with log_path.open("w", encoding="utf-8") as log:
            child_env = dict(os.environ)
            # Windows runners may otherwise inherit a legacy console encoding;
            # startup messages and filenames intentionally contain Chinese text.
            child_env["PYTHONUTF8"] = "1"
            child_env["PYTHONIOENCODING"] = "utf-8"
            proc = subprocess.Popen(
                [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port),
                 "--no-open", "--test-mode"],
                cwd=str(root), stdout=log, stderr=subprocess.STDOUT, env=child_env,
            )
            try:
                status, body = fetch(
                    f"http://127.0.0.1:{port}/api/ping", proc=proc, log_path=log_path
                )
                assert status == 200
                assert json.loads(body.decode("utf-8")).get("ok") is True

                status, body = fetch(f"http://127.0.0.1:{port}/api/bootstrap", attempts=2)
                boot = json.loads(body.decode("utf-8"))
                assert status == 200 and isinstance(boot.get("data"), dict) and boot.get("version")

                status, body = fetch(f"http://127.0.0.1:{port}/", attempts=2)
                assert status == 200 and "Scholar Workspace" in body.decode("utf-8", "replace")
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
        print(f"platform smoke test: 全部通过 on {sys.platform} ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
