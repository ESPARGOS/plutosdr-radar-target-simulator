#!/usr/bin/env python3
"""Serve a hardware-free preview of the Pluto web interface."""

import argparse
import json
import math
import mimetypes
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from control import Controller

ROOT = Path(__file__).resolve().parents[1]
ASSETS = {"/" + path.name: path for path in (ROOT / "web").iterdir() if path.is_file()}
ASSETS["/"] = ROOT / "web/index.html"


class Handler(BaseHTTPRequestHandler):
    def send_json(self, value, status=200):
        data = json.dumps(value, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/state":
            with self.server.controller.lock:
                self.send_json(self.server.controller.state())
            return
        path = ASSETS.get(self.path)
        if not path:
            self.send_error(404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header(
            "Content-Type",
            (
                "text/javascript"
                if path.suffix == ".js"
                else mimetypes.guess_type(path)[0] or "application/octet-stream"
            ),
        )
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + self.headers.get("Host", ""):
            self.send_json({"error": "Cross-origin request rejected"}, 403)
            return
        if self.path not in ("/api/apply", "/api/mute"):
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 1024:
                raise ValueError("Invalid request size")
            body = self.rfile.read(length).decode("ascii")
            with self.server.controller.lock:
                result = (
                    self.server.controller.apply_registers(body)
                    if self.path == "/api/apply"
                    else self.server.controller.mute()
                )
            self.send_json(result)
        except (ValueError, UnicodeError) as error:
            self.send_json({"error": str(error)}, 400)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--demo",
        action="store_true",
        default=True,
        help="Preview without hardware (default)",
    )
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--sample-rate", type=float, default=20e6)
    parser.add_argument("--frequency", type=float, default=2380e6)
    args = parser.parse_args()
    args.pluto = None
    if not math.isfinite(args.sample_rate) or args.sample_rate <= 0:
        parser.error("Invalid sample rate")
    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    server.controller = Controller(args)
    print(f"Radar preview: http://{args.bind}:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
