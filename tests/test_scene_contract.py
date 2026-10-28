"""The Python measurement adapter must match the browser's register protocol."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
from scene import validate, encode_scene, parse_registers

for fixture in json.loads((ROOT / "tests/scene-contract.json").read_text()):
    encoded = encode_scene(validate(fixture, fixture["sample_rate_hz"]))
    assert encoded == fixture["wire"], fixture["name"]
    assert parse_registers(encoded)["mask"] == int(fixture["wire"].splitlines()[0])
print("PASS: shared scene contract, signed/half-step rounding and preview wire format")
