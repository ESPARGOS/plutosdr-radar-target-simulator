#!/usr/bin/env python3
"""Extract delayed turn-off responses from nonperiodic single-tone recordings.

The direct-path falling edge provides the time reference. Independent quiet
bursts estimate receiver noise, so later recirculating echoes are not mistaken
for the noise floor. A sufficiently large Doppler tag (e.g. 500 kHz) separates the first echo from direct
leakage and subsequent echoes. This measures the RF envelope, not sub-sample delay accuracy.
"""

import argparse
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import resample_poly


def analyze(path, window_us=300, minimum_contrast=10):
    with np.load(path) as data:
        iq, ticks = data["iq"], data["ticks"]
        rate = float(data["sample_rate"])
        tone = float(data["tone_hz"])
        doppler = float(data["doppler_hz"]) if "doppler_hz" in data else 0.0
        configured_delay = float(data["delay_samples"]) / float(data["pluto_rate"])
    ticks = np.unwrap(ticks.astype(float) * 2 * np.pi / 2**24) * 2**24 / (2 * np.pi)
    ticks = np.rint(ticks).astype(np.int64)
    order = np.argsort(ticks)
    iq, ticks = iq[order], ticks[order]
    analysis_rate = 500000
    step_us = 1e6 / analysis_rate
    decimation = round(rate / analysis_rate)
    if decimation < 1 or not np.isclose(rate / decimation, analysis_rate):
        raise ValueError("The receiver rate must be an integer multiple of 0.5 MSa/s")
    length = round(window_us / step_us)
    if window_us < 40:
        raise ValueError("Use a return window of at least 40 microseconds")
    boundaries = np.r_[0, np.flatnonzero(np.diff(ticks) != 1) + 1, len(ticks)]
    responses, burst_powers = [], []
    for start, stop in zip(boundaries[:-1], boundaries[1:]):
        if stop - start < 12:
            continue
        samples = iq[start:stop].transpose(1, 0, 2).reshape(iq.shape[1], -1)
        if not np.isfinite(samples).all():
            continue
        time = np.arange(samples.shape[-1]) / rate

        def demodulate(frequency):
            return resample_poly(
                samples * np.exp(-2j * np.pi * frequency * time), 1, decimation, axis=-1
            )[:, 8:-8]

        direct = demodulate(tone)
        baseband = demodulate(tone + doppler) if doppler else direct
        burst_powers.append(np.mean(abs(baseband) ** 2))
        contrast = abs(direct[:, :10].mean(axis=-1)) - abs(
            direct[:, -10:].mean(axis=-1)
        )
        receiver = int(np.argmax(contrast))
        if contrast[receiver] < minimum_contrast:
            continue
        envelope = gaussian_filter1d(abs(direct[receiver]), 2 / step_us)
        edge = int(np.argmin(np.diff(envelope)))
        if edge * step_us < 10 or edge + length >= baseband.shape[-1]:
            continue
        responses.append(np.mean(abs(baseband[:, edge : edge + length]) ** 2, axis=0))
    if not responses:
        raise ValueError("No complete falling-edge recordings with enough contrast")
    burst_powers = np.asarray(burst_powers)
    quiet = burst_powers[burst_powers <= np.quantile(burst_powers, 0.2)]
    noise = float(np.median(quiet))
    responses = np.asarray(responses) - noise
    mean = responses.mean(axis=0)
    # Avoid the direct-path turn-off transient when normalizing the echo.
    end = max(20, min(70, round(configured_delay * 1e6 * 0.65)))
    scale = float(np.mean(mean[round(15 / step_us) : round(end / step_us)]))
    if scale <= 0:
        raise ValueError(
            "No positive delayed echo power after the direct path turns off"
        )
    return dict(
        time_us=np.arange(length, dtype=float) * step_us,
        mean_power=mean / scale,
        event_power=responses / scale,
        events=len(responses),
        configured_delay_us=configured_delay * 1e6,
        doppler_hz=doppler,
        analysis_rate_hz=analysis_rate,
        noise_power=noise,
        echo_power=scale,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--window-us", type=float, default=300)
    parser.add_argument("--minimum-contrast", type=float, default=10)
    args = parser.parse_args()
    result = analyze(args.capture, args.window_us, args.minimum_contrast)
    destination = args.capture.with_name(args.capture.stem + "-envelope.npz")
    np.savez_compressed(destination, **result)
    print(f"Saved {result['events']} complete turn-off responses to {destination}")


if __name__ == "__main__":
    main()
