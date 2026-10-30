"""Run the real CGI parser/control code against an injected I/O backend."""

import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/tests"
BUILD.mkdir(parents=True, exist_ok=True)
cc = os.environ.get("CC", "cc")
common = [cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-Ihost", "-Itests"]
subprocess.run(
    common
    + [
        f'-DRADAR_READY_FILE="{BUILD / "radar-ready"}"',
        f'-DRADAR_FAILED_FILE="{BUILD / "radar-failed"}"',
        f'-DRADAR_STARTUP_FILE="{BUILD / "radar-startup-state"}"',
        f'-DRADAR_FALLBACK_FILE="{BUILD / "radar-fallback"}"',
        "host/radar_cgi.c",
        "host/radar_control.c",
        "host/radar_motion.c",
        f'-DRADAR_MOTION_FILE="{BUILD / "motion.state"}"',
        "tests/fake_device.c",
        "tests/fake_linux.c",
        "-lm",
        "-o",
        str(BUILD / "cgi-test"),
    ],
    cwd=ROOT,
    check=True,
)


def request(path, body=b"", ready=True, failed=False, fallback=False, **faults):
    for filename, present in (
        ("radar-ready", ready),
        ("radar-failed", failed),
        ("radar-fallback", fallback),
    ):
        file = BUILD / filename
        file.unlink(missing_ok=True)
        if present:
            file.touch()
    env = os.environ.copy()
    env.update(
        REQUEST_METHOD="GET" if path == "state" else "POST",
        PATH_INFO="/" + path,
        CONTENT_LENGTH=str(len(body)),
        HTTP_HOST="pluto.test",
        **faults,
    )
    result = subprocess.run(
        [str(BUILD / "cgi-test")], input=body, capture_output=True, env=env, check=True
    )
    headers, payload = result.stdout.split(b"\r\n\r\n", 1)
    code = (
        int(headers.splitlines()[0].split()[1])
        if headers.startswith(b"Status:")
        else 200
    )
    state = (
        json.loads(result.stderr.split(b"TEST_STATE=", 1)[1])
        if b"TEST_STATE=" in result.stderr
        else None
    )
    return code, json.loads(payload), state


code, response, hardware = request("mute", RADAR_TEST_NO_RADIO="1")
assert code == 200 and response["muted"] and not response["radio_available"]
assert hardware["mask"] == 0 and not any(t["enabled"] for t in response["targets"])
assert response["sample_rate_hz"] is None
for attribute in (
    "in_voltage0_hardwaregain_available",
    "in_voltage0_hardwaregain",
    "out_altvoltage0_RX_LO_frequency",
):
    code, response, hardware = request("mute", RADAR_TEST_FAIL_READ=attribute)
    assert code == 200 and hardware["mask"] == 0 and response["warning"]
code, response, hardware = request("mute", RADAR_TEST_BUSY="1")
assert code == 503 and hardware["writes"] == 0
for body in (b"rx nan", b"rx 30.5", b"tx -0.2", b"tx -30 extra", b"rx 30\0extra"):
    assert request("gain", body)[0] == 400
code, response, hardware = request("gain", b"rx 30", RADAR_TEST_FAIL_WRITE="2")
assert code == 503 and hardware["mode"] == "slow_attack"
assert request("apply", b"0 " + b"0 0 0 " * 4 + b"trailing")[0] == 400
assert request("mute", HTTP_ORIGIN="http://other.test")[0] == 403
assert request("state")[1]["hardware_latency_us"] == 0.325
standard = request("state", fallback=True, RADAR_TEST_RATE="61439999")[1]
assert standard["hardware_latency_us"] == 0.78125 and standard["fallback"]
assert standard["sample_rate_hz"] == 61440000
assert abs(standard["max_delay_us"] - 2047 / 61.44) < 1e-8
assert not request("state", fallback=True)[1]["fallback"]
assert request("state", RADAR_TEST_RATE="100000000")[1]["hardware_latency_us"] is None


startup_file = BUILD / "radar-startup-state"
startup_file.unlink(missing_ok=True)
code, response, hardware = request("state", ready=False, failed=True)
assert code == 503 and "Radar startup failed" in response["error"]
assert hardware is None
assert request("state", ready=False)[0] == 503
now = float(Path("/proc/uptime").read_text().split()[0])
startup_file.write_text(f"{now-90} {now-20} tx_verify\n")
code, response, hardware = request("state", ready=False)
assert code == 503 and hardware is None
assert response["error"] == "Checking TX integrity (5-second startup test)"
assert 90 <= response["startup"]["elapsed_seconds"] <= 92
assert 20 <= response["startup"]["stage_elapsed_seconds"] <= 22
assert not response["startup"]["failed"]
assert request("state", ready=False, failed=True)[1]["startup"]["failed"]
for record in (
    "nan 0 radio",
    "0 inf radio",
    "9 1 radio",
    "0 0 unknown",
    '0 0 "bad',
    "0 0 radio extra",
):
    startup_file.write_text(record)
    response = request("state", ready=False)[1]
    assert response["startup"]["elapsed_seconds"] is None
    assert response["error"] == "Waiting for radar startup"
startup_file.unlink()

for header in (
    "motion 16 0 0 100",
    "motion 1 0 0 0",
    "motion 1 0 0 2048",
    "motion 1 0 0 1 trailing",
):
    assert request("apply", (header + "\n0\n" + "0 0 0\n" * 4).encode())[0] == 400
assert (
    request("apply", ("motion 1 15 15 100\n1\n" + "0 0 100\n" * 4).encode())[0] == 503
)

print(
    "PASS: native CGI failure responses, independent mute, rollback, malformed payloads, origins and startup failure"
)
