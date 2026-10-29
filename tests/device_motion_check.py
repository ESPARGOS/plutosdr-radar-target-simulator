"""Live movement integration check. Changes all targets, then leaves them muted."""

import json
import math
import os
import time
import urllib.request
from pathlib import Path

base = (
    os.environ.get("PLUTO_URL", "http://192.168.2.1").rstrip("/")
    + "/cgi-bin/radar.cgi/"
)


def request(path, body=None):
    with urllib.request.urlopen(
        urllib.request.Request(
            base + path,
            data=body.encode() if body is not None else None,
            headers={"Content-Type": "text/plain"},
        ),
        timeout=8,
    ) as r:
        return json.load(r)


state = request("state")
assert state["motion_available"] and state["sample_rate_hz"] == 160000000
rate, carrier = state["sample_rate_hz"], state["frequency_hz"]
phases = [
    round(-v * 2 * carrier / 299792458 / rate * 2**32) for v in (75, 125, -175, -225)
]
rows = [f"{d} {p & 0xffffffff} 4096" for d, p in zip((20, 40, 60, 80), phases)]
report = {"samples": []}
try:
    request("apply", "motion 15 15 15 100\n15\n" + "\n".join(rows))
    start = time.monotonic()
    while time.monotonic() - start < 5:
        snapshot = request("state")
        targets = snapshot["targets"]
        assert len(targets) == 4 and all(
            t["enabled"] and t["realistic_movement"] for t in targets
        )
        assert all(0 <= t["delay_us"] * rate / 1e6 <= 100.001 for t in targets)
        report["samples"].append(
            {"elapsed": time.monotonic() - start, "targets": targets}
        )
        time.sleep(0.04)
    for index in range(4):
        samples = [s["targets"][index] for s in report["samples"]]
        assert (
            min(s["doppler_hz"] for s in samples)
            < 0
            < max(s["doppler_hz"] for s in samples)
        )
        assert (
            max(s["delay_us"] for s in samples) - min(s["delay_us"] for s in samples)
            > 80 / rate * 1e6
        )
    # Same-direction segments must advance at the configured radial velocity.
    errors = []
    for a, b in zip(report["samples"], report["samples"][1:]):
        dt = b["elapsed"] - a["elapsed"]
        for first, second in zip(a["targets"], b["targets"]):
            if first["doppler_hz"] == second["doppler_hz"]:
                expected = -first["doppler_hz"] * rate / carrier * dt
                actual = (second["delay_us"] - first["delay_us"]) * rate / 1e6
                errors.append(abs(actual - expected))
    assert sorted(errors)[int(len(errors) * 0.95)] < 3, max(errors)
    report["velocity_error_95_samples"] = sorted(errors)[int(len(errors) * 0.95)]
    # A stale scene with no trajectory edits must not teleport moving targets.
    snapshot = request("apply", "motion 15 0 0 100\n15\n" + "\n".join(rows))
    before = report["samples"][-1]["targets"]
    assert all(
        abs(a["delay_us"] - b["delay_us"]) < 25 / rate * 1e6
        for a, b in zip(before, snapshot["targets"])
    )
    # Turning movement off preserves the latest position and Doppler.
    frozen = request("apply", "motion 0 0 0 100\n15\n" + "\n".join(rows))
    time.sleep(0.3)
    assert request("state")["targets"] == frozen["targets"]
    # Mute pauses motion and cannot be undone by the background worker.
    request("apply", "motion 15 15 15 100\n15\n" + "\n".join(rows))
    muted = request("mute", "")
    time.sleep(0.3)
    assert request("state")["targets"] == muted["targets"]
    report["passed"] = True
finally:
    request("apply", "0\n" + "0 0 0\n" * 4)
    request("mute", "")
Path("build/motion-live.json").write_text(json.dumps(report, indent=2) + "\n")
print(
    "PASS: four independent moving targets, both bounce boundaries, stale-edit preservation, movement off and mute"
)
