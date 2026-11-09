"""Control a Pluto over SSH, or hold an in-memory scene for the preview."""

import json
import os
import subprocess
import threading
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[2] / "host"))
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
        self.fraction_bits = 10 if args.demo else 0
        self.max_delay = 12276 if args.demo else 8191

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
        self.fraction_bits = 10 if result.get("version") in (0x00020000, 0x00020001, 0x00020002, 0x00020003) else 0
        self.max_delay = result.get(
            "max_delay_samples", 2047 if result.get("version") == 0x00010010 else 8191
        )
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
            frequency_min_hz=70e6 if self.args.demo else 325e6,
            frequency_max_hz=6000e6 if self.args.demo else 3800e6,
            rx_bandwidth_hz=20e6 if self.args.demo else None,
            tx_bandwidth_hz=20e6 if self.args.demo else None,
            max_targets=4,
            max_delay_us=self.max_delay / self.args.sample_rate * 1e6,
            delay_step_us=1e6 / self.args.sample_rate / 2**self.fraction_bits,
            fractional_delay_bits=self.fraction_bits,
            doppler_step_hz=self.args.sample_rate / 2**32,
            targets=self.targets,
            clipped=self.clipped,
            revision=self.revision,
            hardware_latency_us=.45 if self.args.demo else None,
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
            encode_scene(
                validate(
                    payload, self.args.sample_rate, self.fraction_bits, self.max_delay
                )
            )
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
