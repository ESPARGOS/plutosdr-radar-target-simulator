#!/usr/bin/env python3
"""Recover a delay sweep despite independent receiver phases and channel fades."""

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_delay_sweep import analyze


def main():
    rng = np.random.default_rng(817)
    fs, fpga_rate, size = 20e6, 160e6, 256
    bins = np.r_[np.arange(-120, 0), np.arange(1, 121)]
    frequencies = bins * fs / size
    offsets = np.array([0, 0.125, 0.75048828125, 1, 0.5, 0])
    words = -456
    fd = words * fpga_rate / 2**32
    ids = np.repeat(np.arange(len(offsets)), 300)
    ticks = np.arange(len(ids), dtype=np.int64) * 448
    times = ticks * 256 / fs
    channel = (0.2 + rng.random((3, len(bins)))) * np.exp(
        1j * rng.uniform(-np.pi, np.pi, (3, len(bins)))
    )
    channel[:, 85:100] *= 1e-4
    echo = channel[None] * np.exp(
        -2j
        * np.pi
        * (np.floor(offsets * 1024 + 0.5) / 1024)[ids, None, None]
        / fpga_rate
        * frequencies
    )
    # Each edit may have an arbitrary constant phase on each receiver.
    echo *= np.exp(1j * rng.uniform(-0.5, 0.5, (len(offsets), 3)))[ids, :, None]
    echo *= np.exp(2j * np.pi * fd * times[:, None, None])
    # Deep fades contain unrelated noise, so their phases cannot be unwrapped
    # with the useful subcarriers. The resulting delay must remain unbiased.
    echo[..., 85:100] += 0.003 * (
        rng.standard_normal(echo[..., 85:100].shape)
        + 1j * rng.standard_normal(echo[..., 85:100].shape)
    )
    echo += 20 * (1 + 0.2j)
    spectrum = np.zeros((len(ids), 3, size), complex)
    spectrum[..., bins % size] = echo
    path = ROOT / "build/tests/synthetic-delay-sweep.npz"
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        path,
        iq=np.fft.ifft(spectrum, axis=-1),
        bins=bins,
        sample_rate=fs,
        ticks=ticks,
        reference=np.ones(size),
        segment_ids=ids,
        segments=json.dumps(
            [dict(index=i, offset_samples=float(v)) for i, v in enumerate(offsets)]
        ),
        scene=json.dumps({"targets": [{"delay_us": 6.25}]}),
        fpga_status=json.dumps(
            {
                "targets": [{"phase_increment": words % 2**32}],
                "sample_rate_hz": fpga_rate,
            }
        ),
    )
    try:
        result = analyze(path)
        assert result["doppler_hz"] < 0
        assert max(abs(p["error_ps"]) for p in result["points"]) < 2, result
        # Bracketing references remove slow instrument drift, not target delay.
        with np.load(path) as saved:
            fields = {key: saved[key] for key in saved.files}
        drifting = spectrum.copy()
        drifting[..., bins % size] = (echo - 20 * (1 + 0.2j)) * np.exp(
            -2j * np.pi * 0.08e-9 * times[:, None, None] * frequencies
        ) + 20 * (1 + 0.2j)
        fields["iq"] = np.fft.ifft(drifting, axis=-1)
        np.savez(path, **fields)
        raw = analyze(path)
        assert max(abs(point["error_ps"]) for point in raw["points"]) > 500
        corrected = analyze(path, bracketed_reference=True)
        assert (
            max(abs(point["error_ps"]) for point in corrected["points"]) < 5
        ), corrected
        assert corrected["reference_correction"]["reference_indices"] == [0, 5]
    finally:
        path.unlink(missing_ok=True)
    print(
        "PASS: fractional delay sweep with channel fades, receiver phase offsets, negative Doppler and bracketed RF drift correction"
    )


if __name__ == "__main__":
    main()
