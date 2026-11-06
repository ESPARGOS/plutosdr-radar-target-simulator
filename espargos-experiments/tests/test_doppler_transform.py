"""Check fast and irregular-time transforms against the matched-filter sum."""

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from doppler_transform import doppler_response

rng = np.random.default_rng(91)
for irregular in (False, True):
    time = np.arange(431) * 0.0262144
    if irregular:
        time = np.delete(time, [31, 102, 103, 301])
    frequencies = np.linspace(-18, 18, 1257)
    samples = rng.normal(size=(len(time), 3, 11)) + 1j * rng.normal(
        size=(len(time), 3, 11)
    )
    samples += 4 * np.exp(2j * np.pi * 10.99 * time)[:, None, None]
    window = np.hanning(len(time))
    expected = (
        np.einsum(
            "ft,tak->fak",
            np.exp(-2j * np.pi * frequencies[:, None] * time[None]) * window[None],
            samples,
        )
        / window.sum()
    )
    actual = doppler_response(samples, time, frequencies)
    np.testing.assert_allclose(actual, expected, rtol=1e-9, atol=1e-10)
print(
    "PASS: regular and missing snapshots agree with timestamp-based matched filtering"
)
