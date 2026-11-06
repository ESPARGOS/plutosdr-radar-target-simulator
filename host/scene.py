"""Scene/register conversion for Python measurement tools and the preview backend.

The browser sends the same register protocol to both preview and device APIs.
The shared contract fixtures check rounding against the browser implementation.
"""

import math
import re

MAX_TARGETS = 4
MAX_DELAY = 16383
PHASE_SCALE = 2**32


def nearest(value):
    """Match JavaScript Math.round, including negative half-way values."""
    return math.floor(value + 0.5)


def validate(payload, rate, fraction_bits=0, max_delay=MAX_DELAY):
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
        maximum_us = max_delay * 1e6 / rate
        enabled = target.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be boolean")
        if (
            delay < 0
            or (delay > maximum_us and not math.isclose(delay, maximum_us, rel_tol=1e-12))
            or not -rate / 2 < doppler < rate / 2
            or not -90 <= gain <= 0
        ):
            raise ValueError("Target value out of range")
        scale = 2**fraction_bits
        units = nearest(delay * rate / 1e6 * scale)
        samples = units // scale
        fraction = (units % scale) * (65536 // scale)
        phase = nearest(doppler / rate * PHASE_SCALE)
        amplitude = min(32767, nearest(32768 * 10 ** (gain / 20)))
        targets.append(
            dict(
                id=index + 1,
                enabled=enabled,
                delay_us=(samples + fraction / 65536) * 1e6 / rate,
                doppler_hz=phase * rate / PHASE_SCALE,
                gain_db=(
                    max(-90, 20 * math.log10(amplitude / 32768)) if amplitude else -90
                ),
                delay_samples=samples,
                phase_increment=phase,
                gain_q15=amplitude,
                **({"fraction_q16": fraction} if fraction_bits else {}),
            )
        )
    return targets


def encode_scene(targets):
    mask = sum(1 << index for index, target in enumerate(targets) if target["enabled"])
    fractional = any("fraction_q16" in target for target in targets)
    rows = []
    for target in targets:
        words = [
            target["delay_samples"],
            target["phase_increment"] & 0xFFFFFFFF,
            target["gain_q15"],
        ]
        if fractional:
            words.append(target.get("fraction_q16", 0))
        rows.append(" ".join(map(str, words)))
    rows.extend(["0 0 0 0" if fractional else "0 0 0"] * (MAX_TARGETS - len(rows)))
    return "\n".join((["fractional"] if fractional else []) + [str(mask)] + rows)


def parse_registers(text):
    words = text.split()
    fractional = bool(words and words[0] == "fractional")
    if fractional:
        words = words[1:]
    stride = 4 if fractional else 3
    if len(words) != 1 + MAX_TARGETS * stride or any(
        not re.fullmatch(r"[0-9]+", word) for word in words
    ):
        raise ValueError("Expected a mask and four register rows")
    values = [int(word) for word in words]
    if values[0] > 15 or any(value > 0xFFFFFFFF for value in values):
        raise ValueError("Register value out of range")
    targets = []
    for index in range(MAX_TARGETS):
        row = values[1 + stride * index : 1 + stride * (index + 1)]
        delay, phase, gain = row[:3]
        fraction = row[3] if fractional else 0
        if delay > MAX_DELAY or gain > 32767 or phase == 0x80000000 or fraction > 65535:
            raise ValueError("Target value out of range")
        targets.append(
            dict(
                delay_samples=delay,
                phase_increment=phase if phase < 2**31 else phase - PHASE_SCALE,
                gain_q15=gain,
                **({"fraction_q16": fraction} if fractional else {}),
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
                delay_us=(
                    target["delay_samples"] + target.get("fraction_q16", 0) / 65536
                )
                * 1e6
                / rate,
                doppler_hz=target["phase_increment"] * rate / PHASE_SCALE,
                gain_db=max(-90, 20 * math.log10(gain / 32768)) if gain else -90,
                **target,
            )
        )
    return targets
