#!/usr/bin/env python3
"""Separate RX-baseband mirror bins from source-transmitter mirror bins.

For isolated RX results all Pluto targets must be muted and its TX attenuated.
Active-target captures can include a reflected Pluto TX image at the same bin.
"""

import argparse, json
from pathlib import Path
import numpy as np
from analyze_raw_spurs import adc_offset


def measure(x, fs, tones):
    n = len(x)
    offset, ratio = adc_offset(x, fs, tones)
    actual = (tones + offset) * ratio
    w = np.hanning(n)
    z = abs(np.fft.fft(x * w)) ** 2 / w.sum() ** 2

    def power(freq):
        return float(
            sum(z[(round(v * n / fs) + np.arange(-2, 3)) % n].sum() for v in freq)
        )

    reference = power(actual)

    def dbc(p):
        return float(10 * np.log10(max(p, 1e-30) / reference))

    result = dict(
        rx_lo_offset_hz=offset,
        clock_ratio=ratio,
        input_peak=float(max(abs(x.real).max(), abs(x.imag).max())),
        bins_width_hz=5 * fs / n,
    )
    for label, f in [
        ("rx_mirror", -actual),
        ("source_tx_mirror", (-tones + offset) * ratio),
    ]:
        p = power(f)
        floor = (power(f + 8 * fs / n) + power(f - 8 * fs / n)) / 2
        result[label] = dict(
            power_dbc=dbc(p),
            nearby_floor_dbc=dbc(floor),
            excess_dbc=dbc(p - floor) if p > floor else None,
        )
    return result


def analyze(path):
    d = np.load(path)
    s = json.loads(str(d["fpga_status"]))
    cfg = json.loads(str(d["capture_settings"]))
    if not cfg.get("two_tone"):
        raise ValueError("Requires two-tone ADC snapshot")
    fs = s["sample_rate_hz"]
    tones = d["bins"] * float(d["sample_rate"]) / len(d["reference"])
    result = dict(
        capture=str(path),
        sample_rate_hz=fs,
        pluto_targets_muted=s["mask"] == 0,
        tx_attenuation_db=cfg["pluto_tx_attenuation"],
        **measure(d["pluto_input"], fs, tones)
    )
    if "adc_snapshots" in d:
        result["timecourse"] = [
            dict(elapsed_s=float(t), **measure(x, fs, tones))
            for t, x in zip(d["adc_snapshot_times"], d["adc_snapshots"])
        ]
    result["scope"] = (
        "RX image plus reflected TX image if targets active; source mirror separated using measured LO offset"
    )
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("captures", nargs="+", type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    results = [analyze(path) for path in a.captures]
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(results, indent=2) + "\n")
    for r in results:
        print(r["capture"], r["pluto_targets_muted"], r["rx_mirror"])


if __name__ == "__main__":
    main()
