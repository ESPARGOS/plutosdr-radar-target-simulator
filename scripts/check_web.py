#!/usr/bin/env python3
"""Run the preview browser regression without connecting to hardware."""
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
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def ready(url, process):
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError(f'Test service exited: {url}; see build/tests logs')
        try:
            with urllib.request.urlopen(url, timeout=1):
                return
        except OSError:
            time.sleep(.1)
    raise RuntimeError(f'Timed out waiting for {url}')


def main():
    browser = os.environ.get('CHROMIUM_BIN') or shutil.which('chromium') or shutil.which('google-chrome')
    if not browser:
        raise SystemExit('Install Chromium or set CHROMIUM_BIN')
    scratch = Path(os.environ.get('RTS_SCRATCH_DIR', ROOT / 'build/scratch')).resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    logs = ROOT / 'build/tests'
    logs.mkdir(parents=True, exist_ok=True)
    port, debug_port = free_port(), free_port()
    base = f'http://127.0.0.1:{port}'
    env = os.environ.copy()
    env.update(TMPDIR=str(scratch), RADAR_PREVIEW_URL=base, RADAR_BROWSER_DEBUG_PORT=str(debug_port))
    processes = []
    with tempfile.TemporaryDirectory(prefix='browser-', dir=scratch) as profile:
        with (logs/'preview-server.log').open('w') as server_log, (logs/'preview-browser.log').open('w') as browser_log:
            try:
                server = subprocess.Popen([sys.executable, 'host/server.py', '--demo', '--port', str(port)], cwd=ROOT, env=env, stdout=server_log, stderr=subprocess.STDOUT)
                processes.append(server)
                ready(base+'/api/state', server)
                browser_process = subprocess.Popen([browser, '--headless', '--no-sandbox', '--disable-gpu', f'--remote-debugging-port={debug_port}', f'--remote-allow-origins=http://localhost:{debug_port}', f'--user-data-dir={profile}', base], env=env, stdout=browser_log, stderr=subprocess.STDOUT)
                processes.append(browser_process)
                ready(f'http://localhost:{debug_port}/json', browser_process)
                subprocess.run([sys.executable, 'tests/browser_check.py'], cwd=ROOT, env=env, check=True)
            finally:
                for process in reversed(processes):
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


if __name__ == '__main__':
    main()
