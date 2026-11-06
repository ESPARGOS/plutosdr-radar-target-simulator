"""Check causal turn-off timing and separation of recirculating echoes."""

import importlib.util
from pathlib import Path
import tempfile

import numpy as np

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "envelope", root / "scripts/analyze_envelope.py"
)
envelope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(envelope)
rate, tone, delay_us = 4e6, 625e3, 200
(root / "build/tests").mkdir(parents=True, exist_ok=True)
for doppler in (0, 500000):
    rng = np.random.default_rng(54)
    chunks, ticks = [], []
    for burst in range(60):
        time = np.arange(4096) / rate
        iq = np.zeros_like(time, dtype=complex)
        if burst % 3 == 0:
            for amplitude, end, frequency in (
                (100, 100e-6, tone),
                (20, 300e-6, tone + doppler),
                (4, 500e-6, tone + 2 * doppler),
            ):
                iq += amplitude * (time < end) * np.exp(2j * np.pi * frequency * time)
        iq += rng.normal(size=len(time)) + 1j * rng.normal(size=len(time))
        chunks.extend(iq.reshape(16, 1, 256))
        ticks.extend((np.arange(16) + burst * 1024 + 2**24 - 4096) % 2**24)
    with tempfile.TemporaryDirectory(dir=root / "build/tests") as directory:
        capture = Path(directory) / "edges.npz"
        np.savez(
            capture,
            iq=chunks,
            ticks=ticks,
            sample_rate=rate,
            tone_hz=tone,
            delay_samples=12276,
            pluto_rate=12276 / (delay_us * 1e-6),
            doppler_hz=doppler,
        )
        result = envelope.analyze(capture)
    assert result["events"] == 20
    power, time = result["mean_power"], result["time_us"]
    nearby = np.flatnonzero((time >= 180) & (time < 220))
    edge = time[nearby[np.argmin(np.diff(power[nearby]))]]
    assert abs(edge - delay_us) <= 4, edge
    assert 0.95 < np.mean(power[(time >= 30) & (time < 160)]) < 1.05
    tail = np.mean(power[(time >= 230) & (time < 290)])
    if doppler:
        assert abs(tail) < 0.005, "A frequency tag must separate the recirculating echo"
    else:
        assert (
            0.015 < tail < 0.045
        ), "The untagged recirculating echo must remain visible"
    assert 0 < result["noise_power"] < 1
print(
    "PASS: nonperiodic turn-off timing, timestamp wrap, noise estimate and echo frequency separation"
)
