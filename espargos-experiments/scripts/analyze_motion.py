#!/usr/bin/env python3
"""Measure moving-echo phase fluctuations from a two-tone ESPARGOS recording.

The known target Doppler is removed at each recorded timestamp. A low-pass
filter then separates the echo from direct leakage and nearby static clutter.
The reported error is a band-limited relative phase measurement, not a calibrated
RF EVM specification. Both comparison captures must use the same analysis-filter bandwidth.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from scipy import signal


def analyze(path, bandwidth=15.0):
    with np.load(path) as data:
        iq = data["iq"]
        bins = data["bins"]
        if len(bins) != 2:
            raise ValueError("Motion phase analysis requires a two-tone recording")
        fs = float(data["sample_rate"])
        carrier = float(data["frequency"])
        scene = json.loads(str(data["scene"]))
        status = json.loads(str(data["fpga_status"]))
        if len(scene["targets"]) != 1:
            raise ValueError("Use a single target to isolate motion errors")
        phase_word = status["targets"][0]["phase_increment"]
        signed_word = (phase_word + 2**31) % 2**32 - 2**31
        fd = signed_word * status["sample_rate_hz"] / 2**32
        moving = scene["targets"][0].get("realistic_movement", False)
        if "trajectory" in data:
            for snapshot in json.loads(str(data["trajectory"])):
                target = snapshot["targets"][0]
                if (
                    not target["enabled"]
                    or target.get("realistic_movement", False) != moving
                    or abs(target["doppler_hz"] - fd) > 1e-5
                ):
                    raise ValueError(
                        "The target changed direction or settings during the recording; "
                        "use a constant-velocity segment for phase analysis"
                    )
        ticks = (
            np.unwrap(data["ticks"].astype(float) * 2 * np.pi / 2**24)
            * 2**24
            / (2 * np.pi)
        )
        times = ticks * 256 / fs
        order = np.argsort(times)
        times, indices = np.unique(times[order], return_index=True)
        iq = iq[order[indices]]
        times -= times[0]
        frequencies = bins * fs / iq.shape[-1]
        channel = (
            np.fft.fft(iq, axis=-1)[..., bins % iq.shape[-1]]
            / data["reference"][bins % iq.shape[-1]]
        )
    spacing = float(np.median(np.diff(times)))
    sample_rate = 1 / spacing
    expected = fd * (1 + frequencies / carrier) if moving else np.full(2, fd)
    if max(abs(expected)) + bandwidth >= sample_rate / 2:
        raise ValueError(
            f"Doppler/filter band exceeds the {sample_rate/2:.1f} Hz snapshot Nyquist limit"
        )
    if bandwidth <= 0 or bandwidth >= sample_rate / 2:
        raise ValueError("Invalid phase-analysis bandwidth")
    uniform = np.arange(0, times[-1], spacing)
    keep = (uniform >= 1) & (uniform <= uniform[-1] - 1)
    if keep.sum() < 100:
        raise ValueError("At least a few seconds of data are needed")
    sos = signal.butter(4, bandwidth, fs=sample_rate, output="sos")
    output = []
    for index, frequency in enumerate(expected):
        values = channel[..., index] - channel[..., index].mean(axis=0)
        values *= np.exp(-2j * np.pi * frequency * times[:, None])
        resampled = np.stack(
            [
                np.interp(uniform, times, v.real)
                + 1j * np.interp(uniform, times, v.imag)
                for v in values.T
            ],
            axis=1,
        )
        filtered = signal.sosfiltfilt(sos, resampled, axis=0)[keep]
        gains = filtered.mean(axis=0)
        if np.sum(abs(gains) ** 2) < 1e-20:
            raise ValueError("No coherent moving echo in the requested band")
        combined = (filtered @ gains.conj()) / np.sum(abs(gains) ** 2)
        t = uniform[keep]
        phase = np.unwrap(np.angle(combined))
        slope, intercept = np.polyfit(t, phase, 1)
        residual = phase - (slope * t + intercept)
        corrected = combined * np.exp(-1j * (slope * t + intercept))
        offset = np.fft.fftshift(np.fft.fftfreq(len(t), spacing))
        power = abs(np.fft.fftshift(np.fft.fft(corrected * np.hanning(len(t))))) ** 2
        output.append(
            dict(
                expected_hz=float(frequency),
                measured_hz=float(frequency + slope / (2 * np.pi)),
                phase_rms_rad=float(np.sqrt(np.mean(residual**2))),
                coherent_to_fluctuation_db=float(
                    10
                    * np.log10(
                        abs(corrected.mean()) ** 2
                        / max(np.mean(abs(corrected - corrected.mean()) ** 2), 1e-30)
                    )
                ),
                phase_rad=residual,
                power_db=10 * np.log10(np.maximum(power / power.max(), 1e-12)),
            )
        )
    return (
        uniform[keep] - uniform[keep][0],
        offset,
        frequencies,
        output,
        dict(
            phase_bandwidth_hz=bandwidth,
            snapshot_rate_hz=sample_rate,
            carrier_doppler_hz=fd,
            windows=len(times),
            duration_s=float(times[-1]),
            moving=moving,
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--bandwidth", type=float, default=15)
    args = parser.parse_args()
    times, offset, tones, results, metadata = analyze(args.capture, args.bandwidth)
    summary = {
        **metadata,
        "tones": [
            dict(
                baseband_hz=float(tone),
                **{
                    k: v
                    for k, v in result.items()
                    if k not in ("phase_rad", "power_db")
                },
            )
            for tone, result in zip(tones, results)
        ],
    }
    output = args.capture.with_name(args.capture.stem + f"-phase-{args.bandwidth:g}Hz")
    output.with_suffix(".json").write_text(json.dumps(summary, indent=2) + "\n")
    np.savez_compressed(
        output.with_suffix(".npz"),
        time_s=times,
        offset_hz=offset,
        tones_hz=tones,
        phase_rad=np.stack([r["phase_rad"] for r in results]),
        power_db=np.stack([r["power_db"] for r in results]),
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
