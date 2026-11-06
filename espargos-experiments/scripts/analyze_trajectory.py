#!/usr/bin/env python3
"""Range–time and velocity–time maps from a moving-target OFDM recording.

No target positions enter the power calculation. The recorded target settings
are exported separately for comparison with the measured echoes.
"""

import argparse
import json
from pathlib import Path

import numpy as np

from doppler_transform import doppler_response
from array_combining import reference_weights

C = 299792458.0


def analyze(path, window_seconds=1.0, step_seconds=0.5, array_reference=None,
            range_window=None, array_phase_model="per-bin"):
    with np.load(path) as data:
        iq = data["iq"]
        bins = data["bins"]
        rate = float(data["sample_rate"])
        carrier = float(data["frequency"])
        size = iq.shape[-1]
        ticks = np.unwrap(data["ticks"].astype(float) * 2 * np.pi / 2**24)
        time = (ticks - ticks[0]) * 2**24 / (2 * np.pi) * 256 / rate
        pilots = data["reference"][bins % size]
        direct = (np.fft.fft(data["baseline"], axis=-1)[..., bins % size] / pilots).mean(0)
        trajectory = json.loads(str(data["trajectory"]))
        settings = json.loads(str(data["capture_settings"]))
    weights = None if array_reference is None else reference_weights(
        array_reference, bins * rate / size, iq.shape[1], array_phase_model)
    spacing = np.median(np.diff(time))
    velocity_frequency = np.arange(-0.48 / spacing, 0.48 / spacing, 0.5)
    centers = np.arange(window_seconds / 2, time[-1] - window_seconds / 2, step_seconds)
    range_power, velocity_power = [], []
    fft_size = 2048
    if len(bins) < 2:
        raise ValueError("Range estimation requires at least two occupied subcarriers")
    bin_spacing = int(np.gcd.reduce(np.diff(np.sort(bins))))
    # A uniformly sparse pilot grid repeats the range-response magnitude.
    # In particular, odd bins of a doubled vector do not double the
    # unambiguous range. Export only one unambiguous interval.
    range_indices = np.arange(fft_size)
    range_indices = range_indices[range_indices * bin_spacing < fft_size]
    ranges = range_indices * size / fft_size / rate * C / 2
    selected_ranges = np.ones(len(ranges), bool) if range_window is None else (
        (ranges >= range_window[0]) & (ranges <= range_window[1]))
    if not selected_ranges.any():
        raise ValueError("Range window is outside the unambiguous interval")
    for center in centers:
        selected = abs(time - center) <= window_seconds / 2
        if selected.sum() < 4:
            raise ValueError("Not enough snapshots in a processing window")
        channel = np.fft.fft(iq[selected], axis=-1)[..., bins % size] / pilots
        channel *= direct.conj()[None] / (abs(direct)[None] + 1e-9)
        if weights is not None:
            channel = np.sum(channel * weights[None], axis=1, keepdims=True)
        # Reject stationary leakage independently in each window.
        channel -= channel.mean(0, keepdims=True)
        doppler = doppler_response(channel, time[selected], velocity_frequency)
        spectrum = np.zeros(doppler.shape[:2] + (fft_size,), complex)
        spectrum[..., bins % fft_size] = doppler * np.hanning(len(bins))
        response = np.fft.ifft(spectrum, axis=-1)
        power = np.mean(abs(response) ** 2, axis=1)[:, :len(ranges)]
        # Project the complete range–Doppler map onto each axis. Coherent
        # integration resolves weak echoes without following a known target.
        range_power.append(power.max(axis=0))
        velocity_power.append(power[:, selected_ranges].max(axis=1))
    return dict(
        time_s=centers,
        range_m=ranges,
        velocity_m_s=-velocity_frequency * C / (2 * carrier),
        range_power=np.asarray(range_power),
        velocity_power=np.asarray(velocity_power),
        trajectory=json.dumps(trajectory),
        capture_settings=json.dumps(settings),
        snapshot_spacing_seconds=spacing,
        window_seconds=window_seconds,
        step_seconds=step_seconds,
        receive_combining="incoherent-power" if weights is None else array_phase_model,
        velocity_range_window_m=np.array([ranges[selected_ranges].min(),
                                          ranges[selected_ranges].max()]),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--window", type=float, default=1.0)
    parser.add_argument("--step", type=float, default=0.5)
    parser.add_argument("--array-reference", type=Path,
                        help="Independent single-echo capture for fixed receive combining")
    parser.add_argument("--array-phase-model", choices=("per-bin", "constant"),
                        default="per-bin",
                        help="Use per-bin phases or one frequency-independent phase per receiver")
    parser.add_argument("--range-window", type=float, nargs=2, metavar=("MIN", "MAX"),
                        help="Fixed range interval in meters for the velocity projection")
    args = parser.parse_args()
    if args.window <= 0 or args.step <= 0:
        parser.error("Window and step must be positive")
    result = analyze(args.capture, args.window, args.step, args.array_reference,
                     args.range_window, args.array_phase_model)
    output = args.capture.with_name(args.capture.stem + "-trajectory.npz")
    np.savez_compressed(output, **result)
    print(f"Saved {output}")


if __name__ == "__main__":
    main()
