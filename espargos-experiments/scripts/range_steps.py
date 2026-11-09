#!/usr/bin/env python3
"""Measure and plot small range changes with repeated, reference-bracketed sweeps."""

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import numpy as np

from analyze_delay_sweep import analyze

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "figures"))
from plot_range_steps import plot

C = 299792458.0
RATES = {"standard": 61440000, "overclocked": 160000000}


def positions(rate, span_mm, points):
    # Use exactly representable delays, so the requested and programmed axes agree.
    words = np.floor(np.linspace(0, span_mm, points + 1) * 2e-3 / C * rate * 1024 + .5)
    if np.any(np.diff(words) <= 0):
        raise ValueError("The requested spacing is smaller than a delay increment")
    return words / 1024


def capture(args):
    rate = RATES[args.mode]
    offsets = positions(rate, args.span_mm, args.points)
    scene = args.output / "scene.json"
    if args.execute:
        scene.write_text(json.dumps({"targets": [dict(delay_us=0, doppler_hz=17,
                                 gain_db=-3, enabled=True)]}, indent=2) + "\n")
    for repeat in range(args.start_repeat - 1, args.start_repeat - 1 + args.repeats):
        # Reverse alternate sweeps without changing the bracketing reference.
        order = offsets[1:] if repeat % 2 == 0 else offsets[:0:-1]
        output = args.output / f"{args.mode}-{repeat + 1:02d}.npz"
        if output.exists():
            raise FileExistsError(f"Refusing to overwrite {output}")
        command = [sys.executable, str(ROOT / "scripts/measure_espargos.py"),
                   "--host", args.host, "--pluto", args.pluto,
                   "--pyespargos", str(Path(args.pyespargos).resolve()),
                   "--scene", str(scene), "--output", str(output),
                   "--keep-radio-profile", "--expected-fir-enabled",
                   "1" if args.mode == "overclocked" else "0",
                   "--pluto-sample-rate", str(rate), "--pluto-bandwidth", "56000000",
                   "--frequency", "2385000000", "--sample-rate", "80000000",
                   "--occupied-bins", "88", "--transmitter-bandwidth-mhz", "56",
                   "--accumulation-chunks", "64", "--baseline-seconds", "2",
                   "--seconds", str(args.seconds), "--amplitude", "0.8",
                   "--rx-gain", "15", "--pluto-rx-gain", "35",
                   "--pluto-tx-attenuation", "5", "--delay-sweep-samples",
                   *map(str, [0, *order, 0])]
        print(shlex.join(command), flush=True)
        if args.execute:
            subprocess.run(command, check=True, cwd=ROOT)


def summarize(records):
    """Align independent sweeps by programmed delay, excluding reference captures."""
    requested, measured, drift = [], [], []
    for record in records:
        points = sorted((p for p in record["points"] if p["expected_delay_ns"] > 0),
                        key=lambda p: p["expected_delay_ns"])
        requested.append([p["expected_delay_ns"] * C / 2e6 for p in points])
        measured.append([p["measured_delay_ns"] * C / 2e6 for p in points])
        drift.append(record["points"][-1]["raw_delay_ns"] * C / 2e6)
    if len(records) < 5:
        raise ValueError("At least five independent sweeps are needed for a percentile band")
    if not np.allclose(requested, requested[0], atol=1e-8, rtol=0):
        raise ValueError("All sweeps must use the same requested positions")
    values = np.asarray(measured)
    errors = values - requested[0]
    return dict(repeats=len(records), requested_mm=requested[0], measured_mm=measured,
                median_mm=np.median(values, axis=0).tolist(),
                p10_mm=np.percentile(values, 10, axis=0).tolist(),
                p90_mm=np.percentile(values, 90, axis=0).tolist(),
                reference_return_mm=drift,
                maximum_absolute_error_mm=float(np.abs(errors).max()))


def process(args):
    result = dict(band_percentiles=[10, 90],
                  reference_correction="Linear drift between initial and final zero-delay captures",
                  frequency_hz=2385000000, bandwidth_hz=56000000, modes={})
    for mode in RATES:
        paths = sorted(args.output.glob(f"{mode}-[0-9][0-9].npz"))
        if not paths:
            continue
        records = []
        for path in paths:
            with np.load(path) as raw:
                status = json.loads(str(raw["fpga_status"]))
                if status["clipped"]:
                    raise ValueError(f"FPGA clipping in {path.name}")
                if status["sample_rate_hz"] != RATES[mode]:
                    raise ValueError(f"Wrong operating mode in {path.name}")
            record = analyze(path, bracketed_reference=True)
            path.with_suffix(".json").write_text(json.dumps(record, indent=2) + "\n")
            records.append(record)
        result["modes"][mode] = summarize(records)
        result["modes"][mode]["sample_rate_hz"] = RATES[mode]
    if not result["modes"]:
        raise ValueError("No range-step captures found")
    notes = args.output / "acquisition-notes.json"
    if notes.exists():
        result["acquisition_notes"] = json.loads(notes.read_text())
    summary = args.output / "range-steps.json"
    summary.write_text(json.dumps(result, indent=2) + "\n")
    print(summary)
    plot(result, args.output / "range-steps.pdf")



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["capture", "analyze", "plot"])
    parser.add_argument("--mode", choices=RATES)
    parser.add_argument("--output", type=Path, default=ROOT / "build/range-steps")
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--start-repeat", type=int, default=1,
                        help="First recording number, for resuming or replacing an interrupted acquisition")
    parser.add_argument("--span-mm", type=float, default=100)
    parser.add_argument("--points", type=int, default=10)
    parser.add_argument("--seconds", type=float, default=4)
    parser.add_argument("--host", default=os.environ.get("ESPARGOS_HOST"))
    parser.add_argument("--pluto", default=os.environ.get("PLUTO_HOST", "192.168.2.1"))
    parser.add_argument("--pyespargos", default=os.environ.get("PYESPARGOS_PATH"))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.action == "capture" and not all([args.mode, args.host, args.pyespargos]):
        parser.error("Capture requires --mode, --host and --pyespargos")
    if args.start_repeat < 1 or args.repeats < 1 or args.points < 1 or args.span_mm <= 0 or args.seconds <= 0:
        parser.error("Sweep parameters must be positive")
    if args.action != "capture" or args.execute:
        (ROOT / "build").mkdir(parents=True, exist_ok=True)
        args.output.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "build/matplotlib"))
    if args.action == "capture":
        capture(args)
    elif args.action == "analyze":
        process(args)
    else:
        plot(json.loads((args.output / "range-steps.json").read_text()),
             args.output / "range-steps.pdf")


if __name__ == "__main__":
    main()
