#!/usr/bin/env python3
"""Bound the composite interpolation error across the full standard-mode band."""

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from generate_standard_filters import halfband, fractional

h = halfband() / 131072
coefficients = fractional() / 65536
omega = 2 * np.pi * np.linspace(0, 28e6, 8193) / 61.44e6
worst = 0.0
for phase in (0, 1):
    effective = np.array(
        [np.convolve(np.r_[np.zeros(phase), h], row)[::2] for row in coefficients]
    )
    basis = np.exp(-1j * omega[:, None] * np.arange(effective.shape[1]))
    for start in range(0, 1024, 32):
        mu = np.arange(start, start + 32) / 1024
        response = basis @ effective[start : start + 32].T
        ideal = np.exp(-1j * omega[:, None] * ((50 + mu + phase) / 2))
        worst = max(worst, float(abs(response - ideal).max()))
error_db = 20 * np.log10(worst)
assert error_db < -60.5, error_db
print(
    f"PASS: standard-mode interpolation, worst complex error {error_db:.2f} dB over ±28 MHz"
)
