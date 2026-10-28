"""Independent synthetic OFDM scene to verify the measurement FFT axes."""

import json, subprocess, sys
from pathlib import Path
import numpy as np

root = Path(__file__).resolve().parents[1]
rng = np.random.default_rng(12)
fs = 20e6
n = 256
bins = np.r_[np.arange(-90, 0), np.arange(1, 91)]
ref = np.zeros(n, complex)
ref[bins % n] = np.exp(1j * rng.uniform(-np.pi, np.pi, len(bins)))
static = np.exp(1j * rng.uniform(-np.pi, np.pi, (7, 1))) * np.exp(
    -2j * np.pi * bins[None] * 0.37e-6 * fs / n
)
ticks = np.arange(250) * 1024
t = ticks * 256 / fs
scene = json.loads((root / "config/three-targets.json").read_text())
h = np.broadcast_to(static, (len(t), 7, len(bins))).copy()
for target in scene["targets"]:
    h += (
        0.2
        * static[None]
        * np.exp(2j * np.pi * target["doppler_hz"] * t[:, None, None])
        * np.exp(
            -2j * np.pi * bins[None, None] * (target["delay_us"] + 1.2) * 1e-6 * fs / n
        )
    )
# Strong unrelated motion near, but not at, one programmed Doppler tag.
# A ±2 Hz peak search incorrectly picks this zero-delay return.
h += (
    2
    * static[None]
    * np.exp(
        2j * np.pi * (scene["targets"][0]["doppler_hz"] + 1.875) * t[:, None, None]
    )
)


def iq(response):
    full = np.zeros((*response.shape[:-1], n), complex)
    full[..., bins % n] = response * ref[bins % n]
    return np.fft.ifft(full)


path = root / "build/tests/synthetic.npz"
np.savez(
    path,
    iq=iq(h),
    ticks=ticks,
    baseline=iq(np.broadcast_to(static, (50, 7, len(bins)))),
    reference=ref,
    bins=bins,
    sample_rate=fs,
    scene=json.dumps(scene),
    peaks=np.array([1]),
)
subprocess.run(
    [sys.executable, str(root / "scripts/analyze_measurement.py"), str(path)],
    check=True,
    stdout=subprocess.DEVNULL,
)
r = json.loads(path.with_suffix(".json").read_text())
for x in r["targets"]:
    assert abs(x["measured_doppler_hz"] - x["programmed_doppler_hz"]) < 0.15, x
    assert abs(x["measured_delay_us"] - x["programmed_delay_us"] - 1.2) < 0.02, x
print(
    "PASS: synthetic OFDM resolves all three targets with correct delay and Doppler axes"
)
