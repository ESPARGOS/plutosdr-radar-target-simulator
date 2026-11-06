"""Independent calibration recovers coherent array gain without selecting peaks."""

import json
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from array_combining import reference_weights

rate, size, receivers = 16e6, 64, 7
bins = np.r_[np.arange(-16, 0), np.arange(1, 17)]
frequencies = bins * rate / size
ticks = np.arange(512) * 1000
time = ticks * 256 / rate
word = round(17 * 2**32 / rate)
doppler = word * rate / 2**32
phase = 2 * np.pi * np.arange(receivers) / receivers
direct = np.exp(1j * np.arange(receivers)[:, None] * 0.31) * np.ones(
    (receivers, len(bins))
)
echo = direct * np.exp(1j * phase[:, None]) * np.exp(-2j * np.pi * frequencies * 0.7e-6)
channel = direct[None] + np.exp(2j * np.pi * doppler * time[:, None, None]) * echo[None]
pilots = np.ones(size, complex)
spectrum = np.zeros((len(time), receivers, size), complex)
spectrum[..., bins % size] = channel
baseline = np.zeros((1, receivers, size), complex)
baseline[..., bins % size] = direct

with tempfile.TemporaryDirectory(
    dir=Path(__file__).resolve().parents[1] / "build"
) as temporary:
    path = Path(temporary) / "reference.npz"
    np.savez(
        path,
        iq=np.fft.ifft(spectrum, axis=-1),
        baseline=np.fft.ifft(baseline, axis=-1),
        bins=bins,
        sample_rate=rate,
        reference=pilots,
        ticks=ticks,
        scene=json.dumps({"targets": [{"enabled": True}]}),
        fpga_status=json.dumps(
            {"mask": 1, "sample_rate_hz": rate, "targets": [{"phase_increment": word}]}
        ),
    )
    weights = reference_weights(path, frequencies, receivers)
    signal = np.exp(1j * phase[:, None]) * np.ones((receivers, len(bins)))
    assert np.max(abs(signal.sum(axis=0))) < 1e-12
    assert np.max(abs(abs((weights * signal).sum(axis=0)) - np.sqrt(receivers))) < 1e-3
    assert np.max(abs(np.sum(abs(weights) ** 2, axis=0) - 1)) < 1e-12
    constant = reference_weights(path, frequencies, receivers, "constant")
    assert np.max(abs(constant - constant[:, :1])) == 0
    assert np.max(abs(abs((constant * signal).sum(axis=0)) - np.sqrt(receivers))) < 1e-3
    assert np.max(abs(np.sum(abs(constant) ** 2, axis=0) - 1)) < 1e-12
    # Apply exactly the same weights to an independent noise recording.
    rng = np.random.default_rng(15)
    noise = (
        rng.normal(size=(4000, receivers, len(bins)))
        + 1j * rng.normal(size=(4000, receivers, len(bins)))
    ) / np.sqrt(2)
    assert 0.98 < np.mean(abs((noise * weights).sum(axis=1)) ** 2) < 1.02
    for band, count in [(frequencies, 6), (frequencies * 2, receivers)]:
        try:
            reference_weights(path, band, count)
        except ValueError:
            pass
        else:
            raise AssertionError("Incompatible array calibration was accepted")
print(
    "PASS: independent phase reference recovers seven-channel coherent gain with unit noise gain"
)
