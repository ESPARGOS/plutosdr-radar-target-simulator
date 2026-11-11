"""Exercise live mode changes, readiness gating and persistence; leaves targets muted."""
import json
import os
import time
import urllib.error
import urllib.request

base = os.environ.get("PLUTO_URL", "http://192.168.2.1").rstrip("/")


def request(path, body=None):
    data = None if body is None else body.encode()
    req = urllib.request.Request(base + "/cgi-bin/radar.cgi/" + path, data=data,
                                 headers={"Content-Type": "text/plain"})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


code, original = request("state")
assert code == 200 and original["connected"]
request("mute", "")
for mode, rate in [("standard", 61440000), ("overclocked", 160000000)]:
    # A muted but populated scene must not be reinterpreted at the new sample rate.
    code, _ = request("apply", "0\n100 100 3000\n0 0 0\n0 0 0\n0 0 0\n")
    assert code == 200
    code, state = request("mode", mode)
    assert code == 202 and state["muted"] and not state["connected"]
    assert request("apply", "0\n" + "0 0 0\n" * 4)[0] == 503
    assert request("mode", mode)[0] == 503
    deadline = time.monotonic() + 240
    previous = None
    while time.monotonic() < deadline:
        code, state = request("state")
        if code == 200:
            break
        assert code == 503 and not state.get("startup", {}).get("failed"), state
        message = state.get("error")
        if message != previous:
            print(mode + ": " + message, flush=True)
            previous = message
        time.sleep(1)
    assert code == 200, state
    assert state["requested_radio_mode"] == mode
    assert state["sample_rate_hz"] == rate, state
    assert state["radio_mode"] == mode and not state["fallback"]
    assert state["muted"] and not state["targets"]
    for field in ["frequency_hz", "rx_gain_db", "tx_gain_db"]:
        assert abs(state[field] - original[field]) < 1, (field, state[field], original[field])
    assert state["rx_bandwidth_hz"] == original["rx_bandwidth_hz"]
    assert state["tx_bandwidth_hz"] == original["tx_bandwidth_hz"]
    assert state["bandwidth_max_hz"] == 56000000
    expected_latency = (1.35 if mode == "standard" else .45) if original["rx_bandwidth_hz"] == 20000000 else (1.31875 if mode == "standard" else .4140625) if original["rx_bandwidth_hz"] == 56000000 else None
    if expected_latency is not None:
        assert state["hardware_latency_us"] == expected_latency
    else:
        assert .3 < state["hardware_latency_us"] < 5
    print(f"PASS: {mode}, {rate / 1e6:g} MSa/s, {state['hardware_latency_us']} µs, empty muted scene", flush=True)
