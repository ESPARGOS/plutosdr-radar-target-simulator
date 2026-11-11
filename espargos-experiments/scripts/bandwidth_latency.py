#!/usr/bin/env python3
"""Measure zero-added-delay echoes across the analog bandwidth settings."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import urllib.error

import numpy as np
from scipy.optimize import minimize_scalar

ROOT = Path(__file__).resolve().parents[1]
BANDWIDTHS = [.2, .3, .4, .5, .75, 1, 1.5, 2, 3, 5, 8, 12, 16, 20, 25, 30, 40, 50, 56]
RATES = {"standard": 61440000, "overclocked": 160000000}


def estimate_delay(frequencies, response):
    """Locate the echo within one OFDM period, then refine its delay continuously."""
    spacing = np.min(np.diff(frequencies))
    period_us = 1e6 / spacing
    weights = np.hanning(len(frequencies))
    response = response * weights

    def power(delay_us):
        echo = response @ np.exp(2j * np.pi * frequencies * delay_us * 1e-6)
        return np.mean(abs(echo) ** 2)

    grid = np.linspace(0, period_us, 4096, endpoint=False)
    values = np.array([power(delay) for delay in grid])
    peak = grid[np.argmax(values)]
    step = period_us / len(grid)
    fit = minimize_scalar(lambda delay: -power(delay), bounds=(peak-step, peak+step),
                          method="bounded", options={"xatol": 1e-9})
    if not fit.success:
        raise ValueError("Delay fit did not converge")
    return float(fit.x % period_us)


def analyze(path):
    with np.load(path) as data:
        status = json.loads(str(data["fpga_status"]))
        target = status["targets"][0]
        if status["clipped"] or status["mask"] != 1 or target["delay_samples"]:
            raise ValueError("Use one unclipped target with zero added delay")
        rate = status["sample_rate_hz"]
        word = target["phase_increment"]
        doppler = ((word + 2**31) % 2**32 - 2**31) * rate / 2**32
        radio = json.loads(str(data["radio_profile"]))
        fs = float(data["sample_rate"])
        n = data["iq"].shape[-1]
        bins = np.sort(data["bins"])
        frequencies = bins * fs / n
        pilots = data["reference"][bins % n]
        h = np.fft.fft(data["iq"], axis=-1)[..., bins % n] / pilots
        baseline = np.mean(np.fft.fft(data["baseline"], axis=-1)[..., bins % n]
                           / pilots, axis=0)
        ticks = np.unwrap(data["ticks"].astype(float) * 2*np.pi / 2**24) * 2**24 / (2*np.pi)
        times = (ticks - ticks[0]) * 256 / fs
    h -= h.mean(axis=0)
    demodulator = np.hanning(len(times)) * np.exp(-2j*np.pi*doppler*times)
    response = np.einsum("t,trf->rf", demodulator, h)
    response *= np.conj(baseline) / np.maximum(abs(baseline), 1e-20)
    delay = estimate_delay(frequencies, response)
    # Receiver disagreement makes multipath or a weak measurement visible.
    per_receiver = [estimate_delay(frequencies, row[None]) for row in response]
    return dict(sample_rate_hz=rate, rx_bandwidth_hz=radio["rx_rf_bandwidth"],
                tx_bandwidth_hz=radio["tx_rf_bandwidth"], latency_us=delay,
                receiver_delays_us=per_receiver)


def capture(args):
    def api(endpoint, body=None):
        request = urllib.request.Request(f"http://{args.pluto}/cgi-bin/radar.cgi/{endpoint}",
                    data=None if body is None else str(body).encode())
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if endpoint == "state" and error.code == 503:
                return json.load(error)
            raise

    def ready():
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            state = api("state")
            if state.get("connected"):
                return state
            if state.get("startup", {}).get("failed"):
                raise RuntimeError(state["error"])
            time.sleep(2)
        raise RuntimeError("Radio startup timed out")

    def select_mode(mode):
        state = ready()
        if state.get("sample_rate_hz") == RATES[mode]:
            return
        api("mode", mode)
        if ready().get("sample_rate_hz") != RATES[mode]:
            raise RuntimeError(f"{mode} mode did not start")

    initial = ready()
    (args.output / "initial-state.json").write_text(json.dumps(initial, indent=2))
    scene = args.output / "scene.json"
    scene.write_text(json.dumps({"targets": [dict(delay_us=0, doppler_hz=17,
                                               gain_db=-3, enabled=True)]}))
    try:
        for mode in args.modes:
            select_mode(mode)
            for bandwidth in args.bandwidths:
                output = args.output / f"{mode}-{bandwidth:g}.npz"
                if output.exists():
                    raise FileExistsError(output)
                # Narrow filters need a longer waveform to sample their passband.
                fs = 10e6 if bandwidth <= 8 else 20e6 if bandwidth <= 16 else 80e6
                chunks = 4 if bandwidth < 2 else 1
                bins = min(120 * chunks, max(4, int(.4 * bandwidth * 1e6 / (fs/(256*chunks)))))
                command = [sys.executable, str(ROOT / "scripts/measure_espargos.py"),
                    "--host", args.host, "--pluto", args.pluto, "--pyespargos", args.pyespargos,
                    "--scene", str(scene), "--output", str(output), "--keep-radio-profile",
                    "--expected-fir-enabled", "0" if mode == "standard" else "1",
                    "--pluto-sample-rate", str(RATES[mode]), "--pluto-bandwidth", str(round(bandwidth*1e6)),
                    "--frequency", "2385000000", "--sample-rate", str(int(fs)),
                    "--vector-chunks", str(chunks), "--occupied-bins", str(bins),
                    "--transmitter-bandwidth-mhz", "56", "--accumulation-chunks", "64",
                    "--baseline-seconds", "2", "--seconds", "4", "--amplitude", "0.8",
                    "--rx-gain", "15", "--pluto-rx-gain", "35", "--pluto-tx-attenuation", "15"]
                print(f"Measuring {mode}, {bandwidth:g} MHz", flush=True)
                with output.with_suffix(".log").open("w") as log:
                    subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
                result = analyze(output)
                output.with_suffix(".json").write_text(json.dumps(result, indent=2)+"\n")
                print(json.dumps(result), flush=True)
    finally:
        select_mode(initial["requested_radio_mode"])
        api("mute", "")
        api("bandwidth", int(initial["rx_bandwidth_hz"]))
        api("radio", int(initial["frequency_hz"]))
        api("gain", f'rx {initial["rx_gain_db"]}')
        api("gain", f'tx {initial["tx_gain_db"]}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["capture", "analyze"])
    parser.add_argument("--output", type=Path, default=ROOT / "build/bandwidth-latency")
    parser.add_argument("--host", default=os.environ.get("ESPARGOS_HOST"))
    parser.add_argument("--pluto", default=os.environ.get("PLUTO_HOST", "192.168.2.1"))
    parser.add_argument("--pyespargos", default=os.environ.get("PYESPARGOS_PATH"))
    parser.add_argument("--modes", nargs="+", choices=RATES, default=list(RATES))
    parser.add_argument("--bandwidths", type=float, nargs="+", default=BANDWIDTHS)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.action == "capture":
        if not args.host or not args.pyespargos:
            parser.error("Set --host and --pyespargos for capture")
        if any(not .2 <= value <= 56 for value in args.bandwidths):
            parser.error("Bandwidth must be between 0.2 and 56 MHz")
        capture(args)
    else:
        for path in sorted(args.output.glob("*.npz")):
            result = analyze(path)
            path.with_suffix(".json").write_text(json.dumps(result, indent=2)+"\n")
            print(path.name, result["latency_us"])


if __name__ == "__main__":
    main()
