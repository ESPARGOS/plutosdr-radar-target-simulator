"""Known RX and source-TX images separated by a realistic oscillator offset."""

import json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_adc_images import analyze

fs = 160e6
bins = np.array([13, 31])
tones = bins * 20e6 / 256
offset = 33400
ratio = 1.000012
t = np.arange(65536) / fs
desired = sum(np.exp(2j * np.pi * (f + offset) * ratio * t) for f in tones)
source = sum(np.exp(2j * np.pi * (-f + offset) * ratio * t) for f in tones)
x = desired + 0.001 * desired.conj() + 0.03 * source
p = ROOT / "build/tests/adc-image-synthetic.npz"
p.parent.mkdir(parents=True, exist_ok=True)
np.savez(
    p,
    pluto_input=x,
    bins=bins,
    sample_rate=20e6,
    reference=np.zeros(256),
    fpga_status=json.dumps(dict(sample_rate_hz=fs, mask=0)),
    capture_settings=json.dumps(dict(two_tone=True, pluto_tx_attenuation=60)),
)
try:
    r = analyze(p)
    assert r["pluto_targets_muted"]
    assert abs(r["rx_mirror"]["power_dbc"] + 60) < 0.05, r
    assert abs(r["source_tx_mirror"]["power_dbc"] - 20 * np.log10(0.03)) < 0.05, r
    print("PASS: −60 dBc receiver mirror separated from −30.46 dBc source image")
finally:
    p.unlink()
