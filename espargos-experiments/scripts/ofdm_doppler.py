#!/usr/bin/env python3
"""Measure Doppler versus OFDM subcarrier frequency, with and without delay motion."""

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import numpy as np
from scipy import optimize, signal

ROOT = Path(__file__).resolve().parents[1]


def estimate(times, channel, doppler, bandwidth=5):
    """Fit each subcarrier independently. Only a common Doppler is demodulated."""
    order = np.argsort(times)
    times, unique = np.unique(np.asarray(times)[order], return_index=True)
    channel = channel[order[unique]]
    times = times - times[0]
    spacing = float(np.median(np.diff(times)))
    if abs(doppler) + bandwidth >= .5 / spacing:
        raise ValueError("Echo exceeds the snapshot Nyquist frequency")
    if times[-1] < 8 or np.max(np.diff(times)) > .15:
        raise ValueError("Recording is too short or has a long acquisition gap")
    uniform = np.arange(0, times[-1], spacing)
    keep = (uniform >= 1) & (uniform <= uniform[-1] - 1)
    t = uniform[keep]
    centered = t - t.mean()
    nfft = 2**int(np.ceil(np.log2(len(t) * 8)))
    grid = np.fft.fftfreq(nfft, spacing)
    candidates = np.flatnonzero(abs(grid) < bandwidth)
    resolution = 1 / (nfft * spacing)
    sos = signal.butter(4, bandwidth, fs=1 / spacing, output="sos")
    measured, residuals, coherence = [], [], []
    for index in range(channel.shape[-1]):
        values = channel[..., index] - channel[..., index].mean(axis=0)
        values *= np.exp(-2j * np.pi * doppler * times[:, None])
        resampled = np.stack([np.interp(uniform, times, v.real)
                              + 1j * np.interp(uniform, times, v.imag)
                              for v in values.T], axis=1)
        filtered = signal.sosfiltfilt(sos, resampled, axis=0)[keep]
        # Spatial covariance preserves rotation common to all receiver channels.
        # Averaging the complex samples directly could cancel a rotating echo.
        eigenvalues, vectors = np.linalg.eigh(filtered.conj().T @ filtered)
        combined = filtered @ vectors[:, -1]
        # A complex sinusoid fit tolerates brief fades without unwrapping phase
        # through noisy samples. The FFT locates the peak, followed by refinement.
        spectrum = abs(np.fft.fft(combined, nfft)) ** 2
        peak = grid[candidates[np.argmax(spectrum[candidates])]]
        def objective(offset):
            return -abs(np.sum(combined * np.exp(-2j*np.pi*offset*centered))) ** 2
        fit = optimize.minimize_scalar(objective,
            bounds=(peak - 1.5*resolution, peak + 1.5*resolution),
            method="bounded", options={"xatol": 1e-10})
        if not fit.success:
            raise ValueError("Subcarrier frequency fit did not converge")
        corrected = combined * np.exp(-2j*np.pi*fit.x*centered)
        residual = np.angle(corrected * np.exp(-1j*np.angle(corrected.sum())))
        measured.append(float(doppler + fit.x))
        residuals.append(float(np.sqrt(np.mean(residual**2))))
        coherence.append(float(eigenvalues[-1] / eigenvalues.sum()))
    return np.array(measured), dict(phase_residual_rad=residuals,
                                    spatial_coherence=coherence,
                                    duration_s=float(t[-1] - t[0]))


def analyze(path):
    with np.load(path) as data:
        scene = json.loads(str(data["scene"]))
        status = json.loads(str(data["fpga_status"]))
        if len(scene["targets"]) != 1 or status["clipped"] or status["mask"] != 1:
            raise ValueError("Use a single unclipped target")
        target = scene["targets"][0]
        moving = target.get("realistic_movement", False)
        word = status["targets"][0]["phase_increment"]
        doppler = ((word + 2**31) % 2**32 - 2**31) * status["sample_rate_hz"] / 2**32
        trajectory = json.loads(str(data["trajectory"]))
        for entry in trajectory:
            observed = entry["targets"][0]
            if (not observed["enabled"] or observed.get("realistic_movement", False) != moving
                    or abs(observed["doppler_hz"] - doppler) > 1e-5):
                raise ValueError("Target settings or motion direction changed")
        fs = float(data["sample_rate"])
        carrier = float(data["frequency"])
        iq = data["iq"]
        bins = np.sort(data["bins"])
        frequencies = bins * fs / iq.shape[-1]
        if len(bins) < 10 or abs(frequencies.mean()) > 1:
            raise ValueError("Use an OFDM waveform with symmetric occupied subcarriers")
        channel = np.fft.fft(iq, axis=-1)[..., bins % iq.shape[-1]] / data["reference"][bins % iq.shape[-1]]
        ticks = np.unwrap(data["ticks"].astype(float) * 2 * np.pi / 2**24) * 2**24 / (2 * np.pi)
        times = (ticks - ticks[0]) * 256 / fs
    measured, quality = estimate(times, channel, doppler)
    # Symmetric frequencies make this the intercept of an unconstrained linear fit.
    # No expected slope is used to estimate or recenter the measured Dopplers.
    common = measured.mean()
    relative = measured - common
    slope = frequencies @ relative / (frequencies @ frequencies)
    return dict(moving=moving, carrier_hz=carrier, carrier_doppler_hz=doppler,
                frequencies_hz=frequencies.tolist(), measured_hz=measured.tolist(),
                relative_hz=relative.tolist(), common_offset_hz=float(common - doppler),
                measured_slope_hz_per_mhz=float(slope * 1e6),
                expected_slope_hz_per_mhz=float(doppler / carrier * 1e6 if moving else 0),
                **quality)


def capture(args):
    for repeat in range(args.start_repeat, args.start_repeat + args.repeats):
        # Alternate which condition is acquired first to balance slow setup changes.
        modes = ["moving", "fixed"] if repeat % 2 else ["fixed", "moving"]
        for mode in modes:
            output = args.output / f"{mode}-{repeat:02d}.npz"
            if output.exists():
                raise FileExistsError(f"Refusing to overwrite {output}")
            scene = args.output / f"{mode}-scene.json"
            if args.execute:
                scene.write_text(json.dumps({"targets": [dict(delay_us=6.25, doppler_hz=40,
                    gain_db=-3, enabled=True, realistic_movement=mode == "moving")]}, indent=2) + "\n")
            command = [sys.executable, str(ROOT / "scripts/measure_espargos.py"),
                       "--host", args.host, "--pluto", args.pluto,
                       "--pyespargos", str(Path(args.pyespargos).resolve()),
                       "--scene", str(scene), "--output", str(output),
                       "--keep-radio-profile", "--expected-fir-enabled", "1",
                       "--pluto-sample-rate", "160000000", "--pluto-bandwidth", "56000000",
                       "--frequency", "2385000000", "--sample-rate", "80000000",
                       "--occupied-bins", "88", "--transmitter-bandwidth-mhz", "56",
                       "--accumulation-chunks", "64", "--baseline-seconds", "2",
                       "--seconds", str(args.seconds), "--amplitude", "0.8",
                       "--rx-gain", "15", "--pluto-rx-gain", "35", "--pluto-tx-attenuation", "5"]
            print(shlex.join(command), flush=True)
            if args.execute:
                subprocess.run(command, check=True, cwd=ROOT)


def process(args):
    result = dict(band_percentiles=[10, 90], modes={})
    for mode in ["moving", "fixed"]:
        records = []
        for path in sorted(args.output.glob(f"{mode}-[0-9][0-9].npz")):
            record = analyze(path)
            if record["moving"] != (mode == "moving"):
                raise ValueError("Capture condition differs from its filename")
            path.with_suffix(".json").write_text(json.dumps(record, indent=2) + "\n")
            records.append(record)
        if len(records) < 5:
            raise ValueError("At least five recordings per condition are needed for percentiles")
        frequencies = np.array(records[0]["frequencies_hz"])
        if any(r["frequencies_hz"] != frequencies.tolist() for r in records):
            raise ValueError("Subcarrier frequencies differ between recordings")
        if any(r["carrier_hz"] != records[0]["carrier_hz"] or
               r["carrier_doppler_hz"] != records[0]["carrier_doppler_hz"] for r in records):
            raise ValueError("Carrier or target Doppler changed between recordings")
        values = np.array([r["relative_hz"] for r in records])
        prediction = frequencies * records[0]["expected_slope_hz_per_mhz"] / 1e6
        result["modes"][mode] = dict(repeats=len(records), carrier_hz=records[0]["carrier_hz"],
            carrier_doppler_hz=records[0]["carrier_doppler_hz"],
            frequencies_hz=frequencies.tolist(),
            relative_hz=values.tolist(), expected_hz=prediction.tolist(),
            median_hz=np.median(values, axis=0).tolist(),
            p10_hz=np.percentile(values, 10, axis=0).tolist(),
            p90_hz=np.percentile(values, 90, axis=0).tolist(),
            slopes_hz_per_mhz=[r["measured_slope_hz_per_mhz"] for r in records],
            expected_slope_hz_per_mhz=records[0]["expected_slope_hz_per_mhz"],
            common_offsets_hz=[r["common_offset_hz"] for r in records],
            maximum_absolute_median_error_hz=float(np.max(abs(np.median(values,axis=0)-prediction))))
    (args.output / "ofdm-doppler.json").write_text(json.dumps(result, indent=2) + "\n")
    sys.path.insert(0, str(ROOT / "figures"))
    from plot_ofdm_doppler import plot
    plot(result, args.output / "ofdm-doppler.pdf")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["capture", "analyze"])
    parser.add_argument("--output", type=Path, default=ROOT / "build/ofdm-doppler")
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--start-repeat", type=int, default=1)
    parser.add_argument("--seconds", type=float, default=20)
    parser.add_argument("--host", default=os.environ.get("ESPARGOS_HOST"))
    parser.add_argument("--pluto", default=os.environ.get("PLUTO_HOST", "192.168.2.1"))
    parser.add_argument("--pyespargos", default=os.environ.get("PYESPARGOS_PATH"))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.action == "capture" and not all([args.host, args.pyespargos]):
        parser.error("Capture requires --host and --pyespargos")
    if args.repeats < 1 or args.start_repeat < 1 or args.seconds < 10:
        parser.error("Use positive repeat counts and at least ten seconds per capture")
    args.output = args.output.resolve()
    if args.action != "capture" or args.execute:
        args.output.mkdir(parents=True, exist_ok=True)
        (ROOT / "build").mkdir(exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "build/matplotlib"))
    if args.action == "capture":
        capture(args)
    else:
        process(args)


if __name__ == "__main__":
    main()
