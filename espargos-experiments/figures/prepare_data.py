#!/usr/bin/env python3
"""Extract anonymous plot data from the repeated hardware measurements."""

import argparse
import json
from pathlib import Path
import numpy as np
from scipy.signal import welch
from scipy.integrate import trapezoid

ROOT = Path(__file__).resolve().parent.parent


def extract_trajectory(path, output, latency_us):
    with np.load(path) as data:
        snapshots = json.loads(str(data["trajectory"]))
        carrier = json.loads(str(data["capture_settings"]))["frequency"]
        window = data["velocity_range_window_m"]
        keep = (data["range_m"] >= window[0] - 15) & (data["range_m"] <= window[1] + 20)
        ranges = [[(t["delay_us"] + latency_us) * 299792458 / 2e6
                   for t in record["targets"]] for record in snapshots]
        velocities = [[-t["doppler_hz"] * 299792458 / (2 * carrier)
                       for t in record["targets"]] for record in snapshots]
        np.savez_compressed(
            output / "trajectory.npz", time_s=data["time_s"],
            range_m=data["range_m"][keep], velocity_m_s=data["velocity_m_s"],
            range_power=data["range_power"][:, keep].astype(np.float32),
            velocity_power=data["velocity_power"].astype(np.float32),
            command_time_s=[record["time_s"] for record in snapshots],
            command_range_m=ranges, command_velocity_m_s=velocities,
            window_seconds=data["window_seconds"], step_seconds=data["step_seconds"],
            receive_combining=data.get("receive_combining", "per-bin"),
            velocity_range_window_m=window, hardware_latency_us=latency_us,
            carrier_hz=carrier, snapshot_spacing_seconds=data["snapshot_spacing_seconds"],
        )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("measurements", type=Path)
    p.add_argument("--range", dest="range_capture", default="packed-range-sensitive")
    p.add_argument("--range-latency-us", type=float, required=True,
                   help="Hardware-delay reference for the range-map recording")
    p.add_argument("--sweep-prefix", default="review-clean-sweep")
    p.add_argument("--motion-prefix", default="review")
    p.add_argument("--trajectory", help="Stem of an analyzed moving-target recording")
    p.add_argument("--trajectory-latency-us", type=float)
    a = p.parse_args()
    if a.trajectory and a.trajectory_latency_us is None:
        p.error("The trajectory requires its hardware-delay reference")
    source, output = a.measurements, ROOT / "data"
    output.mkdir(exist_ok=True)
    if a.trajectory:
        extract_trajectory(source / (a.trajectory + "-trajectory.npz"), output,
                           a.trajectory_latency_us)
    with np.load(source / (a.range_capture + "-response.npz")) as d:
        keep = d["delay_us"] <= 85
        np.savez_compressed(
            output / "four-targets.npz",
            delay_us=d["delay_us"][keep],
            doppler_hz=d["doppler_hz"],
            power_db=d["power_db"][:, keep].astype(np.float32),
        )
    with np.load(source / (a.range_capture + ".npz")) as d:
        scene = json.loads(str(d["scene"]))
    summary = json.loads((source / (a.range_capture + ".json")).read_text())
    settings = dict(
        normalization_db=max(t["relative_peak_db"] for t in summary["targets"]),
        hardware_delay_us=a.range_latency_us,
        targets=[
            dict(delay_us=t["delay_us"], doppler_hz=t["doppler_hz"])
            for t in scene["targets"]
            if t.get("enabled", True)
        ],
    )
    (output / "four-target-settings.json").write_text(
        json.dumps(settings, indent=2) + "\n"
    )
    sweeps = [
        json.loads((source / f"{a.sweep_prefix}-{i}-delay.json").read_text())
        for i in range(1, 6)
    ]
    requested = [p["expected_delay_ns"] for p in sweeps[0]["points"]]
    for sweep in sweeps:
        assert [p["expected_delay_ns"] for p in sweep["points"]] == requested
    errors = np.array([[p["error_ps"] for p in s["points"]] for s in sweeps])
    repeats = dict(
        requested_ns=requested,
        error_ps=errors.tolist(),
        reference_index=0,
        repeats=5,
        maximum_error_ps=float(abs(errors[:, 1:]).max()),
        maximum_mean_error_ps=float(abs(errors[:, 1:].mean(0)).max()),
        maximum_sd_ps=float(errors[:, 1:].std(0, ddof=1).max()),
    )
    (output / "fractional-repeatability.json").write_text(
        json.dumps(repeats, indent=2) + "\n"
    )
    summary = {}
    grid = np.linspace(-5, 5, 2001)
    for label in ["integer", "fractional", "static"]:
        records, spectra = [], []
        for i in range(1, 4):
            stem = source / f"{a.motion_prefix}-{label}-{i}-phase-5Hz"
            record = json.loads(stem.with_suffix(".json").read_text())
            with np.load(stem.with_suffix(".npz")) as d:
                rate = 1 / np.median(np.diff(d["time_s"]))
                frequency, density = welch(
                    d["phase_rad"][1], fs=rate, nperseg=1024, noverlap=512
                )
                band = (frequency >= 1) & (frequency <= 5)
                record["rms_1_to_5_hz_rad"] = float(
                    np.sqrt(trapezoid(density[band], frequency[band]))
                )
                spectra.append(
                    np.array(
                        [
                            np.interp(grid, d["offset_hz"], 10 ** (v / 10))
                            for v in d["power_db"]
                        ]
                    )
                )
                tones = d["tones_hz"]
            records.append(record)
        power = np.mean(spectra, axis=0)
        power /= power.max(axis=-1, keepdims=True)
        np.savez_compressed(
            output / f"motion-{label}.npz",
            offset_hz=grid,
            tones_hz=tones,
            power_db=10 * np.log10(np.maximum(power, 1e-30)),
        )
        values = [r["rms_1_to_5_hz_rad"] for r in records]
        summary[label] = dict(
            records=records,
            rms_mean_rad=float(np.mean(values)),
            rms_sd_rad=float(np.std(values, ddof=1)),
        )
    (output / "motion.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: {n: v for n, v in d.items() if n != "records"}
                for k, d in summary.items()
            },
            indent=2,
        )
    )
    print(
        json.dumps(
            {k: v for k, v in repeats.items() if k not in ["requested_ns", "error_ps"]},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
