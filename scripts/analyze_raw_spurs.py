#!/usr/bin/env python3
"""Unaveraged RF spectra, retaining Pluto images displaced by the RX/TX LO offset.

Uses contiguous raw chunks only. Desired echo power is Doppler-demodulated;
spur power is averaged noncoherently, with a separately recorded muted baseline.
This measures the complete antenna/receiver chain, not calibrated intrinsic EVM.
"""

import argparse, json
from pathlib import Path
import numpy as np


def bursts(iq, ticks, chunks=8):
    ticks = np.rint(
        np.unwrap(np.asarray(ticks, dtype=float) * 2 * np.pi / 2**24)
        * 2**24
        / (2 * np.pi)
    ).astype(np.int64)
    order = np.argsort(ticks)
    ticks = ticks[order]
    iq = iq[order]
    if len(np.unique(ticks)) != len(ticks):
        raise ValueError("Duplicate raw chunk indices")
    runs = np.split(np.arange(len(ticks)), np.flatnonzero(np.diff(ticks) != 1) + 1)
    windows = []
    starts = []
    for run in runs:
        for start in range(0, len(run) - chunks + 1, chunks):
            ids = run[start : start + chunks]
            windows.append(np.concatenate(iq[ids], axis=-1))
            starts.append(ticks[ids[0]])
    if len(windows) < 20:
        raise ValueError("Fewer than 20 complete contiguous raw windows")
    return np.asarray(windows), np.asarray(starts)


def adc_offset(x, fs, tones):
    n = len(x)
    s = abs(np.fft.fft(x * np.hanning(n))) ** 2
    f = np.fft.fftfreq(n, 1 / fs)
    actual = []
    for expected in tones:
        candidates = np.flatnonzero(abs(f - expected) < 100000)
        k = candidates[np.argmax(s[candidates])]
        y = np.log(s[(k + np.arange(-1, 2)) % n] + 1e-30)
        delta = 0.5 * (y[0] - y[2]) / (y[0] - 2 * y[1] + y[2])
        from scipy.optimize import minimize_scalar

        time = np.arange(n) / fs
        initial = f[k] + delta * fs / n
        fit = minimize_scalar(
            lambda hz: -abs(np.vdot(np.exp(2j * np.pi * hz * time), x * np.hanning(n)))
            ** 2,
            bounds=(initial - fs / n, initial + fs / n),
            method="bounded",
            options={"xatol": 0.01},
        )
        actual.append(fit.x)
    ratio = (actual[1] - actual[0]) / (tones[1] - tones[0])
    return float((actual[0] - ratio * tones[0]) / ratio), float(ratio)


def analyze(path, chunks=8):
    d = np.load(path)
    settings = json.loads(str(d["capture_settings"]))
    state = json.loads(str(d["fpga_status"]))
    if not settings.get("raw_burst_chunks") or not settings.get("two_tone"):
        raise ValueError("Expected raw two-tone bursts")
    fs = float(d["sample_rate"])
    tones = np.asarray(d["bins"]) * fs / len(d["reference"])
    raw, ticks = bursts(d["iq"], d["ticks"], chunks)
    baseline, _ = bursts(d["baseline"], d["baseline_ticks"], chunks)
    n = raw.shape[-1]
    w = np.hanning(n)

    def fft(x):
        return np.fft.fft((x - x.mean(axis=-1, keepdims=True)) * w, axis=-1) / w.sum()

    z = fft(raw)
    b = fft(baseline)
    t = (ticks - ticks[0]) * 256 / fs
    tag = state["targets"][0]["phase_increment"] * state["sample_rate_hz"] / 2**32
    zc = z - z.mean(axis=0, keepdims=True)
    slow = np.hanning(len(t))
    echo = np.einsum("t,tak->ak", slow * np.exp(-2j * np.pi * tag * t), zc) / slow.sum()
    active_power = np.mean(abs(z) ** 2, axis=(0, 1))
    baseline_power = np.mean(abs(b) ** 2, axis=(0, 1))
    echo_power = np.mean(abs(echo) ** 2, axis=0)

    def power(spectrum, frequencies):
        return float(
            sum(
                spectrum[(int(round(f * n / fs)) + np.arange(-1, 2)) % n].sum()
                for f in frequencies
            )
        )

    reference = power(echo_power, tones)
    if reference <= 0:
        raise ValueError("No Doppler-tagged reference")

    def dbc(p):
        return float(10 * np.log10(max(p, 1e-30) / reference))

    offset, ratio = adc_offset(d["pluto_input"], state["sample_rate_hz"], tones)
    report = {
        "capture": str(path),
        "raw_windows": len(raw),
        "baseline_windows": len(baseline),
        "window_samples": n,
        "pluto_sample_rate_hz": state["sample_rate_hz"],
        "receiver_sample_rate_hz": fs,
        "estimated_rx_lo_offset_hz": offset,
        "clock_ratio": ratio,
        "echo_reference_power": reference,
        "esp_peak": float(d["peaks"].max()),
        "fpga_clipped": state["clipped"],
        "scope": "Noncoherent whole-chain spur powers; shifted group combines Pluto RX/TX images; baseline subtraction is not intrinsic-device deembedding",
    }
    groups = {
        "shifted_pluto_images": -tones - 2 * offset,
        "on_grid_images": -tones,
        "imd3": np.array([2 * tones[0] - tones[1], 2 * tones[1] - tones[0]]),
        "pluto_lo": np.array([-offset]),
    }
    for name, frequencies in groups.items():
        on = power(active_power, frequencies)
        off = power(baseline_power, frequencies)
        floor = 0.5 * (
            power(active_power, frequencies - 4 * fs / n)
            + power(active_power, frequencies + 4 * fs / n)
        )
        report[name] = {
            "frequencies_hz": frequencies.tolist(),
            "active_dbc": dbc(on),
            "baseline_dbc": dbc(off),
            "excess_dbc": dbc(on - off) if on > off else None,
            "nearby_active_floor_dbc": dbc(floor),
        }
    radio = json.loads(str(d["radio_profile"]))
    report["adc_snapshot"] = radio.get("adc_snapshot")
    report["transceiver_overflow_start"] = radio.get("overflow_start")
    report["transceiver_overflow_end"] = radio.get("overflow_end")
    return report, (
        np.fft.fftfreq(n, 1 / fs),
        active_power / reference,
        baseline_power / reference,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("captures", nargs="+", type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--chunks", type=int, default=8)
    a = p.parse_args()
    results = []
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(
        len(a.captures), 1, figsize=(12, 3 * len(a.captures)), squeeze=False
    )
    for path, ax in zip(a.captures, axes[:, 0]):
        result, (f, on, off) = analyze(path, a.chunks)
        results.append(result)
        ax.plot(
            np.fft.fftshift(f) / 1e6,
            np.fft.fftshift(10 * np.log10(on + 1e-30)),
            label="Targets active",
        )
        ax.plot(
            np.fft.fftshift(f) / 1e6,
            np.fft.fftshift(10 * np.log10(off + 1e-30)),
            label="Muted baseline",
            alpha=0.7,
        )
        ax.set(
            title=path.stem,
            xlabel="RF offset (MHz)",
            ylabel="Power / tagged echo (dB)",
            ylim=(-80, 20),
        )
        ax.grid(alpha=0.2)
        ax.legend()
    fig.tight_layout()
    a.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(a.output.with_suffix(".png"), dpi=150)
    a.output.write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
