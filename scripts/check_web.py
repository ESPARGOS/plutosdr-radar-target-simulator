#!/usr/bin/env python3
"""Run browser regressions against a local preview or an explicitly selected Pluto."""

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def startup_error(message, log_path):
    if log_path and log_path.exists():
        # Include the tail so CI failures remain readable without local log access.
        with log_path.open("rb") as log:
            log.seek(max(0, log_path.stat().st_size - 4096))
            output = log.read().decode(errors="replace").strip()
        if output:
            message += f"\n{log_path.name}:\n{output}"
    return RuntimeError(message)


def ready(url, process, log_path=None):
    for _ in range(100):
        if process.poll() is not None:
            raise startup_error(
                f"Test service exited with code {process.returncode}: {url}", log_path
            )
        try:
            with urllib.request.urlopen(url, timeout=1):
                return
        except OSError:
            time.sleep(0.1)
    raise startup_error(f"Timed out waiting for {url}", log_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--device", help="Pluto URL; runs live tests that change radio settings"
    )
    args = parser.parse_args()
    browser = (
        os.environ.get("CHROMIUM_BIN")
        or shutil.which("chromium")
        or shutil.which("google-chrome")
    )
    if not browser:
        raise SystemExit("Install Chromium or set CHROMIUM_BIN")
    scratch = Path(os.environ.get("RTS_SCRATCH_DIR", ROOT / "build/scratch")).resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    logs = ROOT / "build/tests"
    logs.mkdir(parents=True, exist_ok=True)
    port, debug_port = free_port(), free_port()
    base = args.device or f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env.update(
        TMPDIR=str(scratch),
        RADAR_PREVIEW_URL=base,
        PLUTO_URL=base,
        RADAR_BROWSER_DEBUG_PORT=str(debug_port),
    )
    processes = []
    with tempfile.TemporaryDirectory(prefix="browser-", dir=scratch) as profile:
        with (logs / "preview-server.log").open("w") as server_log, (
            logs / "preview-browser.log"
        ).open("w") as browser_log:
            try:
                if not args.device:
                    server = subprocess.Popen(
                        [
                            sys.executable,
                            "host/server.py",
                            "--demo",
                            "--port",
                            str(port),
                        ],
                        cwd=ROOT,
                        env=env,
                        stdout=server_log,
                        stderr=subprocess.STDOUT,
                    )
                    processes.append(server)
                    ready(base + "/api/state", server, logs / "preview-server.log")
                browser_process = subprocess.Popen(
                    [
                        browser,
                        "--headless",
                        "--no-sandbox",
                        "--disable-gpu",
                        f"--remote-debugging-port={debug_port}",
                        f"--remote-allow-origins=http://localhost:{debug_port}",
                        f"--user-data-dir={profile}",
                        base,
                    ],
                    env=env,
                    stdout=browser_log,
                    stderr=subprocess.STDOUT,
                )
                processes.append(browser_process)
                ready(
                    f"http://localhost:{debug_port}/json",
                    browser_process,
                    logs / "preview-browser.log",
                )
                subprocess.run(
                    [
                        sys.executable,
                        (
                            "tests/device_web_check.py"
                            if args.device
                            else "tests/browser_check.py"
                        ),
                    ],
                    cwd=ROOT,
                    env=env,
                    check=True,
                )
            finally:
                for process in reversed(processes):
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


if __name__ == "__main__":
    main()
