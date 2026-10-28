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
        "-DRADAR_TEST",
        "host/radar_cgi.c",
        "host/radar_control.c",
        "tests/fake_device.c",
        "tests/fake_linux.c",
        "-lm",
        "-o",
        str(BUILD / "cgi-test"),
    ],
    cwd=ROOT,
    check=True,
)


def request(path, body=b"", **faults):
    env = os.environ.copy()
    env.update(
        REQUEST_METHOD="GET" if path == "state" else "POST",
        PATH_INFO="/" + path,
        CONTENT_LENGTH=str(len(body)),
        HTTP_HOST="pluto.test",
        **faults
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
print(
    "PASS: native CGI failure responses, independent mute, rollback, malformed payloads and origins"
)
