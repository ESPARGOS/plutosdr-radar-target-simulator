#!/usr/bin/env python3
"""Measure primary and repeated echoes during a fixed-target TX gain sweep."""

import argparse
import json
from pathlib import Path

import numpy as np

from doppler_transform import doppler_response

C = 299792458.0


def analyze(path, window_seconds=2.5):
    with np.load(path) as data:
        iq, bins = data["iq"], data["bins"]
        rate, carrier = float(data["sample_rate"]), float(data["frequency"])
        size = iq.shape[-1]
        pilots = data["reference"][bins % size]
        baseline = np.fft.fft(data["baseline"], axis=-1)[..., bins % size] / pilots
        direct = baseline.mean(0)
        correction = direct.conj() / np.maximum(abs(direct), 1e-12)
        ticks = np.unwrap(data["ticks"].astype(float) * 2 * np.pi / 2**24)
        times = (ticks - ticks[0]) * 2**24 / (2 * np.pi) * 256 / rate
        ids = data["segment_ids"]
        segments = json.loads(str(data["segments"]))
        status = json.loads(str(data["fpga_status"]))
        settings = json.loads(str(data["capture_settings"]))
        scene = json.loads(str(data["scene"]))
    if len(scene.get("targets", [])) != 1 or not segments:
        raise ValueError("Use a TX gain sweep with one fixed, Doppler-tagged target")
    if any("tx_gain_db" not in segment for segment in segments):
        raise ValueError("Recording does not contain a TX gain sweep")
    word = status["targets"][0]["phase_increment"]
    doppler = ((word + 2**31) % 2**32 - 2**31) * status["sample_rate_hz"] / 2**32
    if abs(doppler) < 10:
        raise ValueError("Use a Doppler tag of at least 10 Hz to separate the noise probes")
    offsets = np.array([0, -7, -5, -3, 3, 5, 7])
    frequencies = np.r_[doppler + offsets, 2 * doppler + offsets]
    if max(abs(frequencies)) >= .48 / np.median(np.diff(times)):
        raise ValueError("The repeated echo and noise probes exceed the unambiguous Doppler interval")
    fft_size = 4096
    ranges = np.arange(fft_size) * size / fft_size / rate * C / 2

    def response(indices):
        channel = np.fft.fft(iq[indices], axis=-1)[..., bins % size] / pilots
        channel *= correction[None]
        channel -= channel.mean(0, keepdims=True)
        matched = doppler_response(channel, times[indices], frequencies)
        spectrum = np.zeros((len(frequencies), iq.shape[1], fft_size), complex)
        spectrum[..., bins % fft_size] = matched * np.hanning(len(bins))
        return np.mean(abs(np.fft.ifft(spectrum, axis=-1)) ** 2, axis=1)

    # Locate each echo across the complete unambiguous range in the strongest
    # gain segment. All later measurements use these same range bins.
    reference_segment = max(segments, key=lambda segment: segment["tx_gain_db"])
    reference_power = response(np.flatnonzero(ids == reference_segment["index"]))
    peaks = [int(reference_power[order * len(offsets)].argmax()) for order in range(2)]
    # Independently locate the Doppler peaks at those ranges. The subsequent
    # power comparison uses the exact FPGA frequencies, not fitted frequencies.
    selected = np.flatnonzero(ids == reference_segment["index"])
    channel = np.fft.fft(iq[selected], axis=-1)[..., bins % size] / pilots
    channel *= correction[None]
    channel -= channel.mean(0, keepdims=True)
    range_weights = np.hanning(len(bins))[:, None] * np.exp(
        2j * np.pi * bins[:, None] * np.asarray(peaks)[None] / fft_size) / fft_size
    echo_samples = channel @ range_weights
    limit = .48 / np.median(np.diff(times))
    search = np.arange(-limit, limit, .05)
    echo_spectrum = np.mean(abs(doppler_response(echo_samples, times[selected], search))**2, axis=1)
    measured_doppler = search[echo_spectrum.argmax(axis=0)]
    rows = []
    for segment in segments:
        indices = np.flatnonzero(ids == segment["index"])
        if len(indices) < 4:
            raise ValueError("Too few snapshots in a gain segment")
        count = int((times[indices[-1]] - times[indices[0]]) / window_seconds)
        for window in range(count):
            start = times[indices[0]] + window * window_seconds
            selected = indices[(times[indices] >= start) & (times[indices] < start + window_seconds)]
            if len(selected) < 20:
                continue
            power = response(selected)
            signal, noise = [], []
            for order, peak in enumerate(peaks):
                index = order * len(offsets)
                noise.append(float(power[index + 1:index + len(offsets), peak].mean()))
                signal.append(float(power[index, peak] - noise[-1]))
            snr = [float(10 * np.log10(max(s, 1e-30) / max(n, 1e-30)))
                   for s, n in zip(signal, noise)]
            ratio = (float(10 * np.log10(signal[1] / signal[0]))
                     if min(signal) > 0 else None)
            rows.append(dict(segment=segment["index"], time_s=float(start + window_seconds / 2),
                             tx_gain_db=segment["tx_gain_db"], signal_power=signal,
                             noise_power=noise, snr_db=snr, ratio_db=ratio))
    return dict(carrier_hz=carrier, doppler_hz=doppler,
                echo_ranges_m=[float(ranges[peak]) for peak in peaks],
                measured_doppler_hz=measured_doppler.tolist(),
                window_seconds=window_seconds, source_amplitude=settings.get("amplitude"),
                rows=rows, range_m=ranges.tolist(),
                reference_profiles=[reference_power[i * len(offsets)].tolist() for i in range(2)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--window", type=float, default=2.5)
    args = parser.parse_args()
    if not np.isfinite(args.window) or args.window <= 0:
        parser.error("Window must be positive and finite")
    result = analyze(args.capture, args.window)
    output = args.capture.with_name(args.capture.stem + "-feedback.json")
    output.write_text(json.dumps(result, indent=2) + "\n")
    print("Echo ranges (m):", result["echo_ranges_m"])
    for gain in sorted({row["tx_gain_db"] for row in result["rows"]}):
        rows = [row for row in result["rows"] if row["tx_gain_db"] == gain]
        valid = [row["ratio_db"] for row in rows if row["ratio_db"] is not None and min(row["snr_db"]) >= 6]
        print(f"TX {gain:g} dB: {len(valid)}/{len(rows)} windows above 6 dB SNR", end="")
        if valid:
            print(f", repeated/primary {np.median(valid):.2f} dB", end="")
        print()
    print(f"Saved {output}")


if __name__ == "__main__":
    main()
