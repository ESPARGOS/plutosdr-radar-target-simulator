"""In-memory scene controller for the hardware-free web preview."""

import threading
from scene import validate, encode_scene, parse_registers, decode_registers


class Controller:
    def __init__(self, args):
        self.args = args
        self.lock = threading.Lock()
        self.targets = []
        self.revision = 0
        self.fraction_bits = 10
        self.max_delay = 12276

    def state(self):
        return dict(
            mode="demo",
            connected=True,
            error=None,
            pluto=None,
            sample_rate_hz=self.args.sample_rate,
            frequency_hz=self.args.frequency,
            frequency_min_hz=70e6,
            frequency_max_hz=6000e6,
            rx_bandwidth_hz=20e6,
            tx_bandwidth_hz=20e6,
            max_targets=4,
            max_delay_us=self.max_delay / self.args.sample_rate * 1e6,
            delay_step_us=1e6 / self.args.sample_rate / 2**self.fraction_bits,
            fractional_delay_bits=self.fraction_bits,
            doppler_step_hz=self.args.sample_rate / 2**32,
            targets=self.targets,
            clipped=False,
            revision=self.revision,
            hardware_latency_us=0.45,
            latency_calibrated=False,
        )

    def apply(self, payload):
        return self.apply_registers(
            encode_scene(
                validate(
                    payload, self.args.sample_rate, self.fraction_bits, self.max_delay
                )
            )
        )

    def apply_registers(self, text):
        registers = parse_registers(text)
        self.targets = decode_registers(registers, self.args.sample_rate)
        self.revision += 1
        return self.state()

    def mute(self):
        for t in self.targets:
            t["enabled"] = False
        self.revision += 1
        return self.state()
