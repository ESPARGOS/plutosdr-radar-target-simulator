"""Run the real CGI parser/control code against an injected I/O backend."""

import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/tests"
BUILD.mkdir(parents=True, exist_ok=True)
cc = os.environ.get("CC", "cc")
# Match fortified libc checks on CI, including unused I/O return values.
common = [
    cc,
    "-std=c11",
    "-O2",
    "-D_FORTIFY_SOURCE=2",
    "-Wall",
    "-Wextra",
    "-Werror",
    "-Ihost",
    "-Itests",
]
subprocess.run(
    common
    + [
        f'-DRADAR_READY_FILE="{BUILD / "radar-ready"}"',
        f'-DRADAR_FAILED_FILE="{BUILD / "radar-failed"}"',
        f'-DRADAR_STARTUP_FILE="{BUILD / "radar-startup-state"}"',
        f'-DRADAR_FALLBACK_FILE="{BUILD / "radar-fallback"}"',
        f'-DRADAR_MODE_FILE="{BUILD / "radio-mode"}"',
        f'-DRADAR_SERVICE="{BUILD / "mode-service.sh"}"',
        "host/radar_cgi.c",
        "host/radar_control.c",
        "tests/fake_device.c",
        "tests/fake_linux.c",
        "-Wl,--wrap=fopen",
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
        RADAR_TEST_UPTIME="120.00 0.00\n",
    )
    env.update(faults)
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


assert request("state", RADAR_TEST_MASK="0")[1]["muted"]
assert not request("state", RADAR_TEST_MASK="1")[1]["muted"]
assert request("radio", b"2385000000")[1]["muted"]
assert request("state")[1]["frequency_max_hz"] == 3800000000
assert request("radio", b"6000000000")[0] == 400
extended = request("radio", b"6000000000", RADAR_TEST_EXTENDED="1")
assert extended[0] == 200 and extended[1]["frequency_hz"] == 6000000000
assert extended[1]["frequency_min_hz"] == 70000000
assert extended[1]["frequency_max_hz"] == 6000000000
assert request("radio", b"70000000", RADAR_TEST_EXTENDED="1")[0] == 200
assert request("bandwidth", b"56000000")[0] == 400
assert request("bandwidth", b"20000000")[0] == 200
wide = request("bandwidth", b"56000000", RADAR_TEST_WIDEBAND="1")
assert wide[0] == 200 and wide[1]["wideband_available"]
assert wide[1]["rx_bandwidth_hz"] == 56000000
assert wide[1]["tx_bandwidth_hz"] == 56000000
assert wide[1]["hardware_latency_us"] == 0.4078125 and wide[1]["muted"]
standard_wide = dict(RADAR_TEST_WIDEBAND="1", RADAR_TEST_EIGHT_TAPS="1",
                     RADAR_TEST_RATE="61440000")
assert request("state", **standard_wide)[1]["bandwidth_max_hz"] == 30720000
standard_bandwidth = request("bandwidth", b"30720000", **standard_wide)
assert standard_bandwidth[0] == 200
assert standard_bandwidth[1]["hardware_latency_us"] == 1.0734375
assert request("bandwidth", b"20000000", **standard_wide)[1]["hardware_latency_us"] == 1.090625
assert request("bandwidth", b"30720001", **standard_wide)[0] == 400
fast_bandwidth = request("bandwidth", b"56000000", RADAR_TEST_WIDEBAND="1",
                         RADAR_TEST_EIGHT_TAPS="1")
assert fast_bandwidth[0] == 200 and fast_bandwidth[1]["hardware_latency_us"] == .4140625
assert request("bandwidth", b"20000000", RADAR_TEST_WIDEBAND="1",
               RADAR_TEST_EIGHT_TAPS="1")[1]["hardware_latency_us"] == .45
assert (
    request(
        "bandwidth", b"56000000", RADAR_TEST_WIDEBAND="1", RADAR_TEST_RATE="61440000"
    )[0]
    == 400
)
for payload in (b"0 20000000", b"20000000 56000001", b"-1 20000000", b"20000000 junk", b"20000000 20000000 extra", b"4295167296"):
    assert request("bandwidth", payload, RADAR_TEST_WIDEBAND="1")[0] == 400
custom = request("bandwidth", b"30000000", RADAR_TEST_WIDEBAND="1")
assert custom[0] == 200 and custom[1]["muted"]
assert custom[1]["rx_bandwidth_hz"] == 30000000
assert custom[1]["tx_bandwidth_hz"] == 30000000
assert custom[1]["hardware_latency_us"] is None
assert request("bandwidth", b"10000000")[0] == 200
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
# A new CI runner can be younger than the startup interval being tested.
# Exercise that case without depending on the real machine's uptime.
for now, started, changed in ((45, 5, 25), (120, 30, 100)):
    startup_file.write_text(f"{started} {changed} tx_verify\n")
    clock = {"RADAR_TEST_UPTIME": f"{now}.00 0.00\n"}
    code, response, hardware = request("state", ready=False, **clock)
    assert code == 503 and hardware is None
    assert (
        response["error"] == "Checking TX integrity (5-second startup test)"
    ), response
    assert response["startup"]["elapsed_seconds"] == now - started
    assert response["startup"]["stage_elapsed_seconds"] == now - changed
    assert not response["startup"]["failed"]
    assert request("state", ready=False, failed=True, **clock)[1]["startup"]["failed"]
    fallback = request("state", ready=False, fallback=True, **clock)[1]
    assert fallback["startup"]["fallback"]
    assert fallback["error"].startswith("61.44 MHz fallback: Checking TX integrity")
for record in (
    "-45 25 tx_verify",
    "0 121 radio",
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
    "motion 1 0 0 8192",
    "motion 1 0 0 1 trailing",
):
    assert request("apply", (header + "\n0\n" + "0 0 0\n" * 4).encode())[0] == 400
assert (
    request("apply", ("motion 1 15 15 100\n1\n" + "0 0 100\n" * 4).encode())[0] == 400
)

print(
    "PASS: native CGI failure responses, independent mute, rollback, malformed payloads, origins and startup failure"
)

# Hardware motion needs no host movement daemon. Fractional samples survive the
# parser, shadow registers and coherent snapshot returned to the browser.
fractional = b"motion 1 15 15 8000\nfractional\n1\n100 456 16384 32768\n0 0 0 0\n0 0 0 0\n0 0 0 0\n"
code, response, hardware = request("apply", fractional, RADAR_TEST_FRACTIONAL="1")
assert code == 200 and response["fpga_motion"] and response["motion_available"]
assert response["targets"][0]["realistic_movement"]
assert abs(response["targets"][0]["delay_us"] - 100.5 / 160) < 1e-10
assert response["fractional_delay_bits"] == 10
assert response["hardware_latency_us"] == 0.44375
assert (
    request("state", RADAR_TEST_FRACTIONAL="1", RADAR_TEST_RATE="61440000")[1][
        "hardware_latency_us"
    ]
    == 1.05625
)
assert abs(response["delay_step_us"] - 1 / (160 * 1024)) < 1e-12
assert (
    request(
        "apply", fractional.replace(b"100 456", b"12276 456"), RADAR_TEST_FRACTIONAL="1"
    )[0]
    == 400
)
print("PASS: fractional register protocol, FPGA motion and coherent state readback")

# Mode changes mute synchronously and finish asynchronously. The init script
# (covered separately) owns readiness and hardware recalibration.
mode_file = BUILD / "radio-mode"
mode_file.unlink(missing_ok=True)
service = BUILD / "mode-service.sh"
service.write_text(f'#!/bin/sh\nprintf "%s" "$1" > "{BUILD / "mode-invocation"}"\n')
for body in (b"fast", b"standard\n", b"standard;reboot", b"", b"overclocked x"):
    assert request("mode", body)[0] == 400
assert request("mode", b"standard", HTTP_ORIGIN="http://other.test")[0] == 403
assert request("mode", b"standard", ready=False)[0] == 503
for mode in ("standard", "overclocked"):
    marker = BUILD / "mode-invocation"
    marker.unlink(missing_ok=True)
    code, response, hardware = request("mode", mode.encode())
    assert code == 202 and hardware["mask"] == 0
    assert not response["connected"] and response["muted"]
    assert response["targets"] == [] and response["requested_radio_mode"] == mode
    assert mode_file.read_text() == mode + "\n"
    assert not (BUILD / "radar-ready").exists()
    for _ in range(100):
        if marker.exists(): break
        time.sleep(.01)
    assert marker.read_text() == "reconfigure"
    assert request("state")[1]["requested_radio_mode"] == mode
assert request("mode", b"standard", ready=False, failed=True)[0] == 202
service.unlink()
assert request("mode", b"standard")[0] == 503
mode_file.unlink()
print("PASS: validated persistent mode selection, immediate mute and detached restart")
