#!/usr/bin/env python3
"""Compare tagged broadband transfer functions and their repeatability.

These are antenna-path comparisons, not calibrated network-analyzer results.
Remove only a fitted constant gain and linear phase for shape comparisons;
retain and report the fitted delay. Nearby Doppler bins estimate measurement SNR.
"""

import argparse, json
from pathlib import Path
import numpy as np

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("captures", nargs="+", type=Path)
p.add_argument("--output", required=True, type=Path)
a = p.parse_args()
reports = []
transfers = []
for path in a.captures:
    d = np.load(path)
    state = json.loads(str(d["fpga_status"]))
    settings = json.loads(str(d["capture_settings"]))
    if settings.get("two_tone") or settings.get("mimo"):
        raise ValueError("Use single-transmitter broadband captures")
    bins = d["bins"]
    fs = float(d["sample_rate"])
    frequency = bins * fs / d["iq"].shape[-1]
    tick = np.unwrap(d["ticks"].astype(float) * 2 * np.pi / 2**24) * 2**24 / (2 * np.pi)
    t = (tick - tick[0]) * 256 / fs
    tag = state["targets"][0]["phase_increment"] * state["sample_rate_hz"] / 2**32
    h = (
        np.fft.fft(d["iq"], axis=-1)[..., bins % d["iq"].shape[-1]]
        / d["reference"][bins % d["iq"].shape[-1]]
    )
    h -= h.mean(axis=0, keepdims=True)
    direct = np.mean(
        np.fft.fft(d["baseline"], axis=-1)[..., bins % d["iq"].shape[-1]]
        / d["reference"][bins % d["iq"].shape[-1]],
        axis=0,
    )

    def extract(f, mask):
        w = np.hanning(mask.sum())
        return (
            np.einsum("t,tak->ak", w * np.exp(-2j * np.pi * f * t[mask]), h[mask])
            / w.sum()
        )

    mask = np.ones(len(t), dtype=bool)
    echo = extract(tag, mask)
    noise = (abs(extract(tag + 5, mask)) ** 2 + abs(extract(tag - 5, mask)) ** 2) / 2
    valid = (abs(direct) > 0.1 * np.max(abs(direct), axis=-1, keepdims=True)) & (
        abs(echo) ** 2 > 10 * noise
    )
    transfer = echo / (direct + 1e-30)
    delays = []
    shapes = []
    for ant in range(len(echo)):
        phase = np.unwrap(np.angle(transfer[ant]))
        m = valid[ant]
        if m.sum() > 30:
            fit = np.polyfit(frequency[m], phase[m], 1, w=abs(echo[ant, m]))
            delays.append(float(-fit[0] / (2 * np.pi) * 1e6))
            amp = 20 * np.log10(abs(transfer[ant, m]))
            shapes.append(
                {
                    "receiver": ant,
                    "amplitude_5_95_span_db": float(
                        np.percentile(amp, 95) - np.percentile(amp, 5)
                    ),
                    "phase_residual_rms_rad": float(
                        np.std(phase[m] - np.polyval(fit, frequency[m]))
                    ),
                }
            )
    segments = []
    for start in np.arange(0, t[-1] - 2, 2):
        m = (t >= start) & (t < start + 2)
        if m.sum() < 30:
            continue
        z = extract(tag, m)
        projection = np.vdot(echo, z) / np.vdot(echo, echo)
        segments.append(
            {
                "time_s": float(start + 1),
                "gain_db": float(20 * np.log10(abs(projection))),
                "phase_rad": float(np.angle(projection)),
                "residual_dbc": float(
                    10
                    * np.log10(
                        np.sum(abs(z - projection * echo) ** 2)
                        / np.sum(abs(projection * echo) ** 2)
                    )
                ),
            }
        )
    report = {
        "capture": str(path),
        "fpga_clipped": state["clipped"],
        "sample_rate_hz": state["sample_rate_hz"],
        "duration_s": float(t[-1]),
        "tag_snr_db": float(10 * np.log10(np.sum(abs(echo) ** 2) / np.sum(noise))),
        "phase_fit_delay_us_by_receiver": delays,
        "antenna_transfer_shape_by_receiver": shapes,
        "segments": segments,
    }
    # A recirculated single-target echo acquires the Doppler shift again. Report
    # its possible signature separately; this is not exclusive proof of feedback.
    report["double_tag_dbc"] = float(
        10 * np.log10(np.sum(abs(extract(2 * tag, mask)) ** 2) / np.sum(abs(echo) ** 2))
    )
    report["double_tag_floor_dbc"] = float(
        10
        * np.log10(
            np.sum(
                (
                    abs(extract(2 * tag - 5, mask)) ** 2
                    + abs(extract(2 * tag + 5, mask)) ** 2
                )
                / 2
            )
            / np.sum(abs(echo) ** 2)
        )
    )
    if "radio_profile" in d:
        radio = json.loads(str(d["radio_profile"]))
        report["transceiver_overflow_start"] = radio.get("overflow_start")
        report["transceiver_overflow_end"] = radio.get("overflow_end")
    if "pluto_input" in d and len(d["pluto_input"]):
        levels = np.r_[abs(d["pluto_input"].real), abs(d["pluto_input"].imag)]
        report["pluto_input_peak"] = float(levels.max())
        report["pluto_input_fullscale_fraction"] = float(np.mean(levels >= 2047))
    if segments:
        report["segment_gain_span_db"] = float(np.ptp([x["gain_db"] for x in segments]))
    reports.append(report)
    transfers.append((frequency, transfer, valid))
if len(transfers) > 1:
    f0, h0, m0 = transfers[0]
    for report, (f, h, m) in zip(reports[1:], transfers[1:]):
        assert np.array_equal(f, f0)
        comparisons = []
        for ant in range(len(h)):
            valid = m[ant] & m0[ant]
            ratio = h[ant] / (h0[ant] + 1e-30)
            if valid.sum() < 30:
                continue
            amp = 20 * np.log10(abs(ratio[valid]))
            phase = np.unwrap(np.angle(ratio))[valid]
            fit = np.polyfit(f[valid], phase, 1)
            comparisons.append(
                {
                    "receiver": ant,
                    "bins_used": int(valid.sum()),
                    "gain_change_db": float(np.median(amp)),
                    "amplitude_shape_5_95_span_db": float(
                        np.percentile(amp, 95) - np.percentile(amp, 5)
                    ),
                    "delay_change_us": float(-fit[0] / (2 * np.pi) * 1e6),
                    "phase_residual_rms_rad": float(
                        np.std(phase - np.polyval(fit, f[valid]))
                    ),
                }
            )
        report["comparison_to_first"] = comparisons
a.output.write_text(json.dumps(reports, indent=2) + "\n")
for report in reports:
    print(json.dumps({k: v for k, v in report.items() if k != "segments"}, indent=2))
