#!/usr/bin/env python3
"""Estimate relative delay from the phase slope of a Doppler-tagged echo.

All sweep points share one RF calibration. A separate phase intercept for each
receiver removes constant phase offsets, while the slope across subcarriers
measures delay. This is a relative measurement, not an absolute range calibration.
"""

import argparse
import json
from pathlib import Path

import numpy as np


def relative_delay(reference, response, frequencies):
    product = response * reference.conj()
    weights = (
        abs(reference) ** 2
        * abs(response) ** 2
        / np.maximum(abs(reference) ** 2 + abs(response) ** 2, 1e-30)
    )
    # Deep channel fades provide little phase information.
    weights[weights < 0.01 * weights.max(axis=-1, keepdims=True)] = 0
    # Discard fades before unwrapping. Their nearly random phase must not
    # introduce a 2π jump into otherwise usable subcarriers farther along.
    phases = np.zeros_like(weights)
    for receiver in np.ndindex(weights.shape[:-1]):
        good = weights[receiver] > 0
        if np.count_nonzero(good) < 2:
            raise ValueError("Too few usable subcarriers on a receiver")
        phases[receiver][good] = np.unwrap(np.angle(product[receiver][good]))
    totals = weights.sum(axis=-1, keepdims=True)
    if np.any(totals <= 0):
        raise ValueError("No usable echo on at least one receiver")
    f_center = (
        frequencies - (weights * frequencies).sum(axis=-1, keepdims=True) / totals
    )
    p_center = phases - (weights * phases).sum(axis=-1, keepdims=True) / totals
    denominator = np.sum(weights * f_center**2)
    if denominator <= 0:
        raise ValueError("The usable subcarriers do not span a frequency interval")
    slope = np.sum(weights * f_center * p_center) / denominator
    residual = p_center - slope * f_center
    return -slope / (2 * np.pi), np.sqrt(np.sum(weights * residual**2) / weights.sum())


def analyze(path, bracketed_reference=False):
    with np.load(path) as data:
        segments = json.loads(str(data["segments"]))
        if len(segments) < 2:
            raise ValueError("Recording does not contain a delay sweep")
        scene = json.loads(str(data["scene"]))
        status = json.loads(str(data["fpga_status"]))
        if len(scene["targets"]) != 1:
            raise ValueError("Use a single Doppler-tagged target")
        sample_rate = status["sample_rate_hz"]
        phase_word = status["targets"][0]["phase_increment"]
        signed_word = (phase_word + 2**31) % 2**32 - 2**31
        fd = signed_word * sample_rate / 2**32
        if abs(fd) < 1:
            raise ValueError(
                "Use a nonzero Doppler tag to separate the echo from static leakage"
            )
        iq = data["iq"]
        fs = float(data["sample_rate"])
        bins = data["bins"]
        order = np.argsort(bins)
        frequencies = bins[order] * fs / iq.shape[-1]
        channel = (
            np.fft.fft(iq, axis=-1)[..., bins[order] % iq.shape[-1]]
            / data["reference"][bins[order] % iq.shape[-1]]
        )
        ticks = (
            np.unwrap(data["ticks"].astype(float) * 2 * np.pi / 2**24)
            * 2**24
            / (2 * np.pi)
        )
        times = (ticks - ticks[0]) * 256 / fs
        ids = data["segment_ids"]
    responses = []
    centers = []
    for segment in segments:
        indices = np.flatnonzero(ids == segment["index"])
        indices = indices[np.argsort(times[indices])]
        if len(indices) < 50:
            raise ValueError("Too few windows in a sweep segment")
        h = channel[indices] - channel[indices].mean(axis=0)
        window = np.hanning(len(indices))
        centers.append(float(np.average(times[indices], weights=window)))
        matched = window * np.exp(-2j * np.pi * fd * times[indices])
        responses.append(np.einsum("t,tak->ak", matched, h) / window.sum())
    base_samples = scene["targets"][0]["delay_us"] * sample_rate / 1e6
    positions = (
        np.floor(
            (base_samples + np.array([s["offset_samples"] for s in segments])) * 1024
            + 0.5
        )
        / 1024
    )
    expected = (positions - positions[0]) / sample_rate
    results = []
    for segment, response, requested in zip(segments, responses, expected):
        measured, residual = relative_delay(responses[0], response, frequencies)
        results.append(
            dict(
                index=segment["index"],
                offset_samples=segment["offset_samples"],
                expected_delay_ns=float(requested * 1e9),
                measured_delay_ns=float(measured * 1e9),
                error_ps=float((measured - requested) * 1e12),
                phase_residual_rad=float(residual),
            )
        )
    correction = None
    if bracketed_reference:
        references = np.flatnonzero(positions == positions[0])
        if (
            len(references) < 2
            or references[0] != 0
            or references[-1] != len(results) - 1
        ):
            raise ValueError(
                "A bracketed sweep must start and end at its reference delay"
            )
        drift = np.interp(
            centers,
            np.array(centers)[references],
            [results[i]["measured_delay_ns"] for i in references],
        )
        for point, offset in zip(results, drift):
            point["raw_delay_ns"] = point["measured_delay_ns"]
            point["reference_drift_ns"] = float(offset)
            point["measured_delay_ns"] -= float(offset)
            point["error_ps"] = 1000 * (
                point["measured_delay_ns"] - point["expected_delay_ns"]
            )
        correction = dict(
            method="Linear interpolation between bracketing reference captures",
            reference_indices=references.tolist(),
        )
    return dict(
        sample_rate_hz=sample_rate,
        doppler_hz=fd,
        points=results,
        reference_correction=correction,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument(
        "--bracketed-reference",
        action="store_true",
        help="Correct slow RF delay drift using repeated zero-offset captures",
    )
    args = parser.parse_args()
    result = analyze(args.capture, args.bracketed_reference)
    output = args.capture.with_name(args.capture.stem + "-delay.json")
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
