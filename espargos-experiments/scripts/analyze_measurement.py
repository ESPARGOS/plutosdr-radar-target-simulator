#!/usr/bin/env python3
"""Range/Doppler matched filtering of saved ESPARGOS OFDM captures."""

import argparse, json
from pathlib import Path
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from array_combining import reference_weights
from doppler_transform import doppler_response

p = argparse.ArgumentParser()
p.add_argument("capture")
p.add_argument(
    "--array-reference",
    type=Path,
    help="Independent single-echo capture for fixed coherent receive combining",
)
p.add_argument(
    "--doppler-step", type=float, default=0.125, help="Doppler grid spacing in Hz"
)
p.add_argument(
    "--doppler-limit",
    type=float,
    default=38,
    help="Requested Doppler span, bounded by the capture cadence",
)
p.add_argument(
    "--doppler-tolerance",
    type=float,
    default=0.5,
    help="Search within this many Hz of each programmed Doppler tag (default: 0.5)",
)
a = p.parse_args()
if not np.isfinite(a.doppler_tolerance) or a.doppler_tolerance <= 0:
    p.error("Doppler tolerance must be positive and finite")
if not np.isfinite(a.doppler_step) or a.doppler_step <= 0:
    p.error("Doppler step must be positive and finite")
if not np.isfinite(a.doppler_limit) or a.doppler_limit <= 0:
    p.error("Doppler limit must be positive and finite")
d = np.load(a.capture)
iq = d["iq"]
bins = d["bins"]
fs = float(d["sample_rate"])
n = iq.shape[-1]
tick = d["ticks"].astype(float)
tick = np.unwrap(tick * 2 * np.pi / (1 << 24)) * (1 << 24) / (2 * np.pi)
time = (tick - tick[0]) * 256 / fs
# Long waveform periods reduce the snapshot rate. Keep the displayed Doppler
# interval inside its unambiguous band instead of plotting aliases as echoes.
spacing = np.median(np.diff(np.unique(time)))
limit = np.floor(min(a.doppler_limit, 0.48 / spacing) / a.doppler_step) * a.doppler_step
if 2 * limit / a.doppler_step > 10000:
    p.error("Doppler grid exceeds 10000 points")
freq_grid = np.arange(-limit, limit + a.doppler_step / 2, a.doppler_step)
h = np.fft.fft(iq, axis=-1)[..., bins % n] / d["reference"][bins % n]
baseline = np.fft.fft(d["baseline"], axis=-1)[..., bins % n] / d["reference"][bins % n]
# Align each RX channel to its measured direct path for a common delay origin.
mean_baseline = np.mean(baseline, axis=0)
correction = np.conj(mean_baseline) / (np.abs(mean_baseline) + 1e-9)
h *= correction[None]
# Slow-time clutter rejection. Nonuniform timestamps are handled explicitly.
h -= h.mean(axis=0, keepdims=True)
if a.array_reference:
    weights = reference_weights(a.array_reference, bins * fs / n, h.shape[1])
    h = np.sum(h * weights[None], axis=1, keepdims=True)
doppler = doppler_response(h, time, freq_grid)
full = np.zeros((len(freq_grid), doppler.shape[1], 2048), complex)
full[..., bins % 2048] = doppler * np.hanning(len(bins))[None, None]
response = np.fft.ifft(full, n=2048, axis=-1)
power = np.mean(abs(response) ** 2, axis=1)
delay = np.arange(2048) / fs * n / 2048 * 1e6
power_db = 10 * np.log10(power + 1e-30)
power_db -= power_db.max()
fig, ax = plt.subplots(figsize=(11, 5))
im = ax.pcolormesh(
    delay, freq_grid, power_db, shading="auto", vmin=-45, vmax=0, cmap="magma"
)
ax.set(
    xlabel="Delay relative to measured direct path (µs, modulo OFDM period)",
    ylabel="Doppler (Hz)",
    title="Pluto FPGA echoes observed by ESPARGOS",
)
fig.colorbar(im, ax=ax, label="Relative response (dB)")
fig.tight_layout()
path = Path(a.capture)
fig.savefig(path.with_suffix(".png"), dpi=160)
np.savez_compressed(
    path.with_name(path.stem + "-response.npz"),
    delay_us=delay,
    doppler_hz=freq_grid,
    power_db=power_db,
)
scene = json.loads(str(d["scene"]))
results = []
for target in scene.get("targets", []):
    # A broad search can pick unrelated moving clutter instead of the NCO tag.
    # Select by known Doppler only; do not constrain or subtract the measured delay.
    f = target["doppler_hz"]
    band = abs(freq_grid - f) <= a.doppler_tolerance
    if not np.any(band):
        raise ValueError(f"Doppler {f} Hz is outside the analysis grid")
    sub = power[band]
    fi, di = np.unravel_index(sub.argmax(), sub.shape)
    results.append(
        dict(
            programmed_delay_us=target["delay_us"],
            programmed_doppler_hz=f,
            measured_delay_us=float(delay[di]),
            measured_doppler_hz=float(freq_grid[band][fi]),
            relative_peak_db=float(power_db[band][fi, di]),
        )
    )
summary = dict(
    capture=str(path),
    windows=len(iq),
    duration_s=float(time[-1]),
    peak_adc=float(d["peaks"].max()),
    targets=results,
    receive_combining="fixed reference phases" if a.array_reference else "mean power",
    array_reference=str(a.array_reference) if a.array_reference else None,
    doppler_step_hz=a.doppler_step,
    doppler_limit_hz=float(limit),
)
path.with_suffix(".json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
