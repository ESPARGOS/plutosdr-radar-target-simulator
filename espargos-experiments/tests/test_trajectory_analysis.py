"""A moving echo must follow the same range slope and Doppler velocity."""

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_trajectory import C, analyze

build = ROOT / "build/tests"
build.mkdir(parents=True, exist_ok=True)
path = build / "synthetic-trajectory.npz"
rate, carrier, velocity = 20e6, 2385e6, 4.0
# A doubled vector with odd bins has no DC gap but repeats its range
# magnitude after half the vector period. Check physical delay and Doppler
# scaling for both grids.
for size, bins in [(64, np.r_[np.arange(-25, 0), np.arange(1, 26)]),
                   (128, np.arange(-49, 50, 2))]:
    time = np.arange(1024) / 256
    distance = 150 + velocity * time
    frequency = bins * rate / size
    doppler = -2 * velocity * carrier / C
    channel = 3 + np.exp(-2j * np.pi * frequency[None] * 2 * distance[:, None] / C
                         + 2j * np.pi * doppler * time[:, None])
    spectrum = np.zeros((len(time), 1, size), complex)
    spectrum[:, 0, bins % size] = channel
    direct = np.zeros((4, 1, size), complex)
    direct[:, :, bins % size] = 3
    np.savez(path, iq=np.fft.ifft(spectrum), baseline=np.fft.ifft(direct), bins=bins,
             reference=np.ones(size), sample_rate=rate, frequency=carrier,
             ticks=time * rate / 256, trajectory=json.dumps([]), capture_settings="{}")
    result = analyze(path)
    # Both waveforms have the same occupied-carrier spacing, hence the
    # same ambiguity interval despite their different vector lengths.
    assert result["range_m"][-1] < C * 64 / (2 * rate)
    assert result["range_m"][-1] > .99 * C * 64 / (2 * rate)
    measured_range = result["range_m"][result["range_power"].argmax(axis=1)]
    measured_velocity = result["velocity_m_s"][result["velocity_power"].argmax(axis=1)]
    assert np.max(abs(measured_range - (150 + velocity * result["time_s"]))) < 1
    assert np.max(abs(measured_velocity - velocity)) < .05
print("PASS: moving-echo range and Doppler agree for conventional and half-bin pilot grids")
