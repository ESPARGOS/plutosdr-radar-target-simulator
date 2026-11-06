#!/usr/bin/env python3
"""Check phase analysis against known motion, phase ripple and static leakage."""

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_motion import analyze


def main():
    rng = np.random.default_rng(734)
    fs, carrier, fpga_rate = 20e6, 2385e6, 160e6
    phase_word = 1074
    doppler = phase_word * fpga_rate / 2**32
    # Timestamp jitter, a dropped window and a swapped pair exercise the
    # recorded-time path instead of assuming uniformly spaced input windows.
    ticks = np.arange(1800, dtype=np.int64) * 400
    ticks += rng.integers(-3, 4, len(ticks))
    ticks = np.delete(ticks, 450)
    ticks[[810, 811]] = ticks[[811, 810]]
    times = ticks * 256 / fs
    bins = np.array([13, 110])
    tones = bins * fs / 256
    ripple = 0.1 * np.sin(2 * np.pi * 2 * times)
    channel = np.exp(
        1j
        * (
            2 * np.pi * times[:, None] * (doppler * (1 + tones / carrier))
            + ripple[:, None]
        )
    )
    gains = np.array([1 + 0.3j, -0.5 + 0.8j, 0.2 - 0.7j])
    channel = channel[:, None, :] * gains[None, :, None] + 30 * (1 + 0.4j)
    spectrum = np.zeros((len(ticks), 3, 256), complex)
    spectrum[..., bins] = channel
    iq = np.fft.ifft(spectrum, axis=-1)
    path = ROOT / "build/tests/synthetic-motion.npz"
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        path,
        iq=iq,
        bins=bins,
        sample_rate=fs,
        frequency=carrier,
        ticks=ticks,
        reference=np.ones(256),
        scene=json.dumps({"targets": [{"realistic_movement": True}]}),
        fpga_status=json.dumps(
            {"targets": [{"phase_increment": phase_word}], "sample_rate_hz": fpga_rate}
        ),
    )
    try:
        _, _, _, results, _ = analyze(path, 5)
        for result, frequency in zip(results, doppler * (1 + tones / carrier)):
            assert abs(result["measured_hz"] - frequency) < 0.002, result
            assert abs(result["phase_rms_rad"] - 0.1 / np.sqrt(2)) < 0.004, result
        with np.load(path) as recording:
            reflected = dict(recording)
        reflected["trajectory"] = json.dumps(
            [{"targets": [{"enabled": True, "realistic_movement": True,
                           "doppler_hz": -doppler}]}]
        )
        np.savez(path, **reflected)
        try:
            analyze(path, 5)
        except ValueError as error:
            assert "changed direction" in str(error)
        else:
            raise AssertionError("A reflection cannot be fitted as constant velocity")
    finally:
        path.unlink(missing_ok=True)
    print(
        "PASS: two-tone motion phase with timestamp jitter, missing windows and strong static leakage"
    )


if __name__ == "__main__":
    main()
