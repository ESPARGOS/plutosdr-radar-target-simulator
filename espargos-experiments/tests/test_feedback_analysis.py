"""Recover the doubled delay and gain law of a linear feedback echo."""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_feedback import C, analyze

build = ROOT / "build/tests"
build.mkdir(parents=True, exist_ok=True)
rate, size = 20e6, 64
time = np.arange(18 * 128) / 128
ids = (time // 6).astype(int)
gains = np.array([-12, -18, -24])
bins = np.r_[np.arange(-25, 0), np.arange(1, 26)]
frequency = bins * rate / size
word = 456
doppler = word * 160e6 / 2**32
amplitude = 10 ** ((gains[ids] + 12) / 20)
channel = 3 + amplitude[:, None] * np.exp(
    -2j * np.pi * frequency[None] * 2 * 200 / C + 2j * np.pi * doppler * time[:, None])
channel += .1 * amplitude[:, None]**2 * np.exp(
    -2j * np.pi * frequency[None] * 2 * 400 / C + 4j * np.pi * doppler * time[:, None])
spectrum = np.zeros((len(time), 1, size), complex)
spectrum[:, 0, bins % size] = channel
baseline = np.zeros((4, 1, size), complex)
baseline[..., bins % size] = 3
path = build / "synthetic-feedback.npz"
np.savez(path, iq=np.fft.ifft(spectrum), baseline=np.fft.ifft(baseline),
         bins=bins, reference=np.ones(size), sample_rate=rate, frequency=2385e6,
         ticks=time * rate / 256, segment_ids=ids,
         segments=json.dumps([dict(index=i, tx_gain_db=int(g)) for i, g in enumerate(gains)]),
         fpga_status=json.dumps(dict(sample_rate_hz=160e6, targets=[dict(phase_increment=word)])),
         scene=json.dumps(dict(targets=[dict(delay_us=1, doppler_hz=17)])),
         capture_settings=json.dumps(dict(amplitude=.75)))
result = analyze(path)
assert np.max(abs(np.array(result["echo_ranges_m"]) - [200, 400])) < .5
assert np.max(abs(np.array(result["measured_doppler_hz"]) - doppler * np.array([1, 2]))) < .05
for row in result["rows"]:
    assert abs(row["ratio_db"] - (-20 + row["tx_gain_db"] + 12)) < .1, row
    assert min(row["snr_db"]) > 30
print("PASS: repeated echo has double delay and the expected one-dB-per-dB relative gain law")
