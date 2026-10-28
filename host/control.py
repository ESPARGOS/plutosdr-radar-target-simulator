"""Control a Pluto over SSH, or hold an in-memory scene for the preview."""

import json
import os
import subprocess
import threading
from pathlib import Path
from scene import validate, encode_scene, parse_registers, decode_registers

ROOT = Path(__file__).resolve().parents[1]


class Controller:
    def __init__(self, args):
        self.args = args
        self.lock = threading.Lock()
        self.targets = []
        self.clipped = False
        self.error = None
        self.connected = args.demo
        self.revision = 0

    def call(self, command, stdin=None):
        if self.args.demo:
            return None
        env = os.environ.copy()
        env["SSHPASS"] = os.environ.get("PLUTO_PASSWORD", "analog")
        cmd = [
            "sshpass",
            "-e",
            "ssh",
            "-o",
            "ConnectTimeout=3",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"UserKnownHostsFile={ROOT}/build/known_hosts",
            "-o",
            "LogLevel=ERROR",
            f"root@{self.args.pluto}",
            f'if [ -f /tmp/radar-loaded ]; then /tmp/rtsctl {command}; else echo "Radar FPGA is not loaded; run scripts/deploy.sh" >&2; exit 1; fi',
        ]
        p = subprocess.run(
            cmd, input=stdin, text=True, capture_output=True, timeout=6, env=env
        )
        if p.returncode:
            raise RuntimeError(p.stderr.strip() or "Pluto control failed")
        self.connected = True
        self.error = None
        result = json.loads(p.stdout)
        if result.get("sample_rate_hz"):
            self.args.sample_rate = result["sample_rate_hz"]
        return result

    def state(self):
        return dict(
            mode="demo" if self.args.demo else "hardware",
            connected=self.connected,
            error=self.error,
            pluto=self.args.pluto,
            espargos=None,
            sample_rate_hz=self.args.sample_rate,
            frequency_hz=self.args.frequency,
            rx_bandwidth_hz=20e6 if self.args.demo else None,
            tx_bandwidth_hz=20e6 if self.args.demo else None,
            max_targets=4,
            max_delay_us=2047 / self.args.sample_rate * 1e6,
            delay_step_us=1e6 / self.args.sample_rate,
            doppler_step_hz=self.args.sample_rate / 2**32,
            targets=self.targets,
            clipped=self.clipped,
            revision=self.revision,
            hardware_latency_us=0.325 if self.args.demo else None,
            latency_calibrated=False,
        )

    def refresh(self):
        result = self.call("status")
        if result:
            self.clipped = result["clipped"]
            self.targets = decode_registers(result, self.args.sample_rate)
        return self.state()

    def apply(self, payload):
        if not self.args.demo:
            self.call("status")
        return self.apply_registers(
            encode_scene(validate(payload, self.args.sample_rate))
        )

    def apply_registers(self, text):
        registers = parse_registers(text)
        result = self.call("apply", text + "\n")
        self.targets = decode_registers(result or registers, self.args.sample_rate)
        self.clipped = bool(result and result["clipped"])
        self.revision += 1
        return self.state()

    def mute(self):
        self.call("mute")
        for t in self.targets:
            t["enabled"] = False
        self.revision += 1
        return self.state()
