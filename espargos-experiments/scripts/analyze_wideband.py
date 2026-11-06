#!/usr/bin/env python3
"""Measure the over-the-air echo/direct transfer response of a tagged target.

The direct reference cancels common source and receiver responses. Different
propagation paths and antennas remain, so this is not a de-embedded Pluto RF
specification. Each receiver is normalized by one gain and fitted linear phase.
No frequency-dependent equalization is applied.
"""

import argparse
import json
from pathlib import Path
import numpy as np


def residual_response(frequencies, response, nominal_delay_s=0):
    """Remove one mean gain and a linear phase from each receiver response."""
    gain_db = 20 * np.log10(np.maximum(abs(response), 1e-30))
    gain_db -= gain_db.mean(axis=-1, keepdims=True)
    phase = np.unwrap(
        np.angle(response * np.exp(2j * np.pi * frequencies * nominal_delay_s)), axis=-1
    )
    design = np.column_stack([np.ones(len(frequencies)), frequencies / 1e6])
    fit = np.linalg.lstsq(design, phase.T, rcond=None)[0]
    residual = phase - (design @ fit).T
    return gain_db, residual, nominal_delay_s - fit[1] / (2 * np.pi * 1e6)


def analyze(path, nominal_delay_s):
    with np.load(path) as d:
        iq, baseline = d["iq"], d["baseline"]
        fs = float(d["sample_rate"])
        bins = d["bins"]
        order = np.argsort(bins)
        bins = bins[order]
        frequencies = bins * fs / iq.shape[-1]
        reference = d["reference"][bins % iq.shape[-1]]
        h = np.fft.fft(iq, axis=-1)[..., bins % iq.shape[-1]] / reference
        direct = (
            np.fft.fft(baseline, axis=-1)[..., bins % iq.shape[-1]] / reference
        ).mean(axis=0)
        status = json.loads(str(d["fpga_status"]))
        word = status["targets"][0]["phase_increment"]
        fd = ((word + 2**31) % 2**32 - 2**31) * status["sample_rate_hz"] / 2**32
        ticks = (
            np.unwrap(d["ticks"].astype(float) * 2 * np.pi / 2**24)
            * 2**24
            / (2 * np.pi)
        )
        times = (ticks - ticks[0]) * 256 / fs
        keep = np.ones(len(times), dtype=bool)
        if "segment_ids" in d and len(d["segment_ids"]):
            keep = d["segment_ids"] == 0
        h, times = h[keep], times[keep]
        if len(times) < 50:
            raise ValueError("Too few windows")
        if abs(fd) < 1:
            raise ValueError("Use a Doppler-tagged target")
        w = np.hanning(len(times))
        h -= h.mean(axis=0)
        echo = np.einsum("t,tak->ak", w * np.exp(-2j * np.pi * fd * times), h) / w.sum()
        if np.any(abs(direct) < 1e-4 * abs(direct).max()):
            raise ValueError("Direct reference has a deep fade; do not divide by it")
        response = echo / direct
    gain, phase, delays = residual_response(frequencies, response, nominal_delay_s)
    return dict(frequency_hz=frequencies, gain_db=gain, phase_rad=phase, delay_s=delays)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("capture", type=Path)
    p.add_argument(
        "--delay-us",
        type=float,
        required=True,
        help="Approximate total echo delay, removed before phase unwrapping",
    )
    a = p.parse_args()
    result = analyze(a.capture, a.delay_us * 1e-6)
    np.savez_compressed(a.capture.with_name(a.capture.stem + "-wideband.npz"), **result)
    print(
        json.dumps(
            dict(
                gain_span_db=np.ptp(result["gain_db"], axis=-1).tolist(),
                phase_rms_deg=np.rad2deg(
                    np.sqrt(np.mean(result["phase_rad"] ** 2, axis=-1))
                ).tolist(),
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
