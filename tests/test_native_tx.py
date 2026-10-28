"""Displaced TX image is distinct from the stronger receiver-generated image."""

import json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_native_tx import analyze

fs = 20e6
ticks = np.concatenate([np.arange(8) + i * 8192 for i in range(40)])
t = (ticks[:, None] * 256 + np.arange(256)) / fs
nominal = 5e6
offset = -33400
main = np.exp(2j * np.pi * (nominal + offset) * t)
tx = 0.001 * np.exp(2j * np.pi * (-nominal + offset) * t)
rx = 0.01 * np.exp(-2j * np.pi * (nominal + offset) * t)
iq = (main + tx + rx)[:, None, :]
baseline = np.zeros_like(iq)
p = ROOT / "build/tests/native-tx-synthetic.npz"
p.parent.mkdir(parents=True, exist_ok=True)
np.savez(
    p,
    iq=iq,
    baseline=baseline,
    ticks=ticks,
    baseline_ticks=ticks,
    sample_rate=fs,
    peaks=np.array([10]),
    capture_settings=json.dumps(
        dict(pluto_bist_tone=0, raw_burst_chunks=16, pluto_tx_attenuation=20)
    ),
    fpga_status=json.dumps(dict(sample_rate_hz=160e6, mask=0)),
)
try:
    r = analyze(p)
    assert abs(r["pluto_tx_image"]["power_dbc"] + 60) < 0.2, r
    assert abs(r["espargos_rx_image"]["power_dbc"] + 40) < 0.2, r
    assert abs(r["apparent_lo_offset_hz"] - offset) < 1, r
    print("PASS: native TX −60 dBc image separated from receiver −40 dBc image")
finally:
    p.unlink()
