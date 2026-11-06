"""Check interpolation fidelity independently of the bit-exact RTL oracle."""

import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from generate_fractional_rom import coefficients

fractions = np.arange(1024) / 1024
for fast, rate, bandwidth, bound_db in [(True, 160e6, 56e6, -61), (False, 61.44e6, 30.72e6, -57),
                                       (False, 61.44e6, 20e6, -66)]:
    taps = 6 if fast else 8
    center = taps // 2 - 1
    matrix = np.array([coefficients(i, fast) for i in range(1024)]) / 65536
    assert np.all((matrix[:, 6] * 65536 >= -4096) & (matrix[:, 6] * 65536 < 4096))
    assert np.all((matrix[:, 7] * 65536 >= -512) & (matrix[:, 7] * 65536 < 512))
    assert np.all(matrix.sum(axis=1) == 1)
    assert np.max(np.abs(matrix).sum(axis=1)) < 1.7
    assert np.array_equal(matrix[1:512, :taps], matrix[1023:512:-1, taps-1::-1])
    frequency = np.linspace(0, bandwidth / 2, 4097)
    omega = 2 * np.pi * frequency / rate
    response = matrix @ np.exp(-1j * np.arange(8)[:, None] * omega)
    ideal = np.exp(-1j * (center + fractions[:, None]) * omega)
    error = np.max(np.abs(response - ideal))
    db = 20 * np.log10(error)
    assert db < bound_db, (rate, db)
    print(
        f"PASS: Q2.16 {taps}-tap filter, {rate/1e6:g} MSa/s, worst complex error {db:.2f} dB over ±{bandwidth/2e6:g} MHz"
    )
