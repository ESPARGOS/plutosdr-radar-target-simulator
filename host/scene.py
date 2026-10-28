"""Scene/register conversion for Python measurement tools and the preview backend.

The browser sends the same register protocol to both preview and device APIs.
The shared contract fixtures check rounding against the browser implementation.
"""

import math
import re

MAX_TARGETS = 4
MAX_DELAY = 2047
PHASE_SCALE = 2**32


def nearest(value):
    """Match JavaScript Math.round, including negative half-way values."""
    return math.floor(value + 0.5)


def validate(payload, rate):
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError("Invalid sample clock")
    if not isinstance(payload, dict) or not isinstance(payload.get("targets"), list):
        raise ValueError("Expected a targets array")
    if len(payload["targets"]) > MAX_TARGETS:
        raise ValueError("The FPGA supports four targets")
    targets = []
    for index, target in enumerate(payload["targets"]):
        if not isinstance(target, dict):
            raise ValueError("Invalid target")
        values = [target.get(name) for name in ("delay_us", "doppler_hz", "gain_db")]
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in values
        ):
            raise ValueError("Delay, Doppler and gain must be finite numbers")
        delay, doppler, gain = values
        enabled = target.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be boolean")
        if (
            not 0 <= delay <= MAX_DELAY * 1e6 / rate
            or not -rate / 2 < doppler < rate / 2
            or not -90 <= gain <= 0
        ):
            raise ValueError("Target value out of range")
        samples = nearest(delay * rate / 1e6)
        phase = nearest(doppler / rate * PHASE_SCALE)
        amplitude = min(32767, nearest(32768 * 10 ** (gain / 20)))
        targets.append(
            dict(
                id=index + 1,
                enabled=enabled,
                delay_us=samples * 1e6 / rate,
                doppler_hz=phase * rate / PHASE_SCALE,
                gain_db=(
                    max(-90, 20 * math.log10(amplitude / 32768)) if amplitude else -90
                ),
                delay_samples=samples,
                phase_increment=phase,
                gain_q15=amplitude,
            )
        )
    return targets


def encode_scene(targets):
    mask = sum(1 << index for index, target in enumerate(targets) if target["enabled"])
    rows = [
        f"{target['delay_samples']} {target['phase_increment'] & 0xffffffff} {target['gain_q15']}"
        for target in targets
    ]
    return "\n".join([str(mask), *rows, *(["0 0 0"] * (MAX_TARGETS - len(rows)))])


def parse_registers(text):
    words = text.split()
    if len(words) != 13 or any(not re.fullmatch(r"[0-9]+", word) for word in words):
        raise ValueError("Expected a mask and four register rows")
    values = [int(word) for word in words]
    if values[0] > 15 or any(value > 0xFFFFFFFF for value in values):
        raise ValueError("Register value out of range")
    targets = []
    for index in range(MAX_TARGETS):
        delay, phase, gain = values[1 + 3 * index : 4 + 3 * index]
        if delay > MAX_DELAY or gain > 32767 or phase == 0x80000000:
            raise ValueError("Target value out of range")
        targets.append(
            dict(
                delay_samples=delay,
                phase_increment=phase if phase < 2**31 else phase - PHASE_SCALE,
                gain_q15=gain,
            )
        )
    return dict(mask=values[0], targets=targets)


def decode_registers(registers, rate):
    targets = []
    for index, target in enumerate(registers["targets"]):
        enabled = bool(registers["mask"] & (1 << index))
        gain = target["gain_q15"]
        if not gain and not enabled:
            continue
        targets.append(
            dict(
                id=index + 1,
                enabled=enabled,
                delay_us=target["delay_samples"] * 1e6 / rate,
                doppler_hz=target["phase_increment"] * rate / PHASE_SCALE,
                gain_db=max(-90, 20 * math.log10(gain / 32768)) if gain else -90,
                **target,
            )
        )
    return targets
