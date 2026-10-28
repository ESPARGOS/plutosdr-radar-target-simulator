"""Known two-tone intermodulation and image levels, with strong static clutter."""

import json, subprocess, sys
from pathlib import Path
import numpy as np

root = Path(__file__).resolve().parents[1]
out = root / "build/tests/quality"
out.mkdir(parents=True, exist_ok=True)
fs = 20e6
rate = 110000000
increment = 664
f = rate * increment / 2**32
count = 600
n = 256
ticks = np.arange(count, dtype=np.int64) * 1024
t = ticks * 256 / fs
for lo, hi in [(13, 31), (79, 101)]:
    freq = np.zeros((count, 2, n), complex)
    for b in (lo, hi):
        freq[:, :, b] = np.exp(2j * np.pi * f * t)[:, None]
    for b in (2 * lo - hi, 2 * hi - lo):
        freq[:, :, b % n] = 0.01 * np.exp(2j * np.pi * f * t)[:, None]
    for b in (-lo, -hi):
        freq[:, :, b % n] = (
            0.003162277660168379 * np.exp(2j * np.pi * f * t)
            + 0.001778279410038923 * np.exp(-2j * np.pi * f * t)
        )[:, None]
    freq += 1000  # static direct-path clutter must not be counted as tagged distortion
    capture = out / f"known-{lo}-{hi}.npz"
    result = capture.with_suffix(".json")
    np.savez(
        capture,
        iq=np.fft.ifft(freq, axis=-1),
        ticks=ticks,
        sample_rate=fs,
        peaks=np.ones(count),
        bins=np.array([lo, hi]),
        capture_settings=json.dumps({"two_tone": True}),
        fpga_status=json.dumps(
            {
                "sample_rate_hz": rate,
                "targets": [{"phase_increment": increment}],
                "clipped": False,
            }
        ),
    )
    subprocess.run(
        [
            sys.executable,
            str(root / "scripts/analyze_signal_quality.py"),
            str(capture),
            "--output",
            str(result),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    report = json.loads(result.read_text())[0]
    for field, expected in [
        ("imd3_dbc", -40),
        ("rx_image_dbc", -50),
        ("tx_image_dbc", -55),
    ]:
        assert abs(report[field] - expected) < 0.05, (field, report[field], expected)
    assert report["fundamental_floor_dbc"] < -60
print(
    "PASS: low/edge-band two-tone IMD and image levels with 60 dB stronger static clutter"
)

# An off-grid image with a different slow-time frequency must survive the
# aligned test's noncoherent power estimator rather than disappear at +tag.
ticks = np.arange(count, dtype=np.int64) * 64
t = ticks * 256 / fs
freq = np.zeros((count, 2, n), complex)
baseline = np.zeros_like(freq)
for b in (13, 31):
    freq[:, :, b] = np.exp(2j * np.pi * f * t)[:, None] + 100
    baseline[:, :, b] = 100
for b in (-14, -32):
    freq[:, :, b % n] = 0.01 * np.exp(2j * np.pi * (200 - f) * t)[:, None]
adc_fs = 160e6
adc_t = np.arange(65536) / adc_fs
offset = fs / n / 2 + 100
adc = sum(np.exp(2j * np.pi * (b * fs / n + offset) * adc_t) for b in (13, 31))
capture = out / "known-aligned.npz"
result = capture.with_suffix(".json")
np.savez(
    capture,
    iq=np.fft.ifft(freq, axis=-1),
    baseline=np.fft.ifft(baseline, axis=-1),
    ticks=ticks,
    sample_rate=fs,
    peaks=np.ones(count),
    bins=np.array([13, 31]),
    pluto_input=adc,
    capture_settings=json.dumps({"two_tone": True, "accumulation_chunks": 64}),
    radio_profile=json.dumps({"image_grid_alignment": [{"offset_hz": offset}]}),
    fpga_status=json.dumps(
        {
            "sample_rate_hz": adc_fs,
            "targets": [{"phase_increment": f * 2**32 / adc_fs}],
            "clipped": False,
        }
    ),
)
subprocess.run(
    [
        sys.executable,
        str(root / "scripts/analyze_signal_quality.py"),
        str(capture),
        "--output",
        str(result),
    ],
    check=True,
    stdout=subprocess.DEVNULL,
)
report = json.loads(result.read_text())[0]["shifted_pluto_images"]
assert abs(report["active_dbc"] + 40) < 0.05, report
assert abs(report["end_offset_hz"] - offset) < 0.1, report
expected = -20 * np.log10(np.sinc((200 + f) * 64 * 256 / fs))
assert abs(report["sampled_worst_averaging_loss_db"] - expected) < 0.01, report
print(
    "PASS: aligned image power survives a different Doppler/LO frequency; averaging-loss bound matches analytic sinc"
)
