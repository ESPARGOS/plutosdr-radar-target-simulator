"""Fixed receive combining phases from an independent single-echo recording."""

import json

import numpy as np


def reference_weights(path, frequencies, receiver_count, phase_model="per-bin"):
    """Return phase-only weights, with unit noise gain, for the entire map.

    The reference must use the same antenna order and physical arrangement.
    Its target supplies relative receive phases, not target locations or a
    range-dependent mask. No weights are fitted to the measurement being plotted.
    The constant model estimates one phase per receiver across the reference
    band, avoiding any frequency-dependent phase correction in the combiner.
    """
    if phase_model not in ("per-bin", "constant"):
        raise ValueError("Unknown array phase model")
    with np.load(path) as data:
        iq = data["iq"]
        if iq.shape[1] != receiver_count:
            raise ValueError("Array reference has a different receiver count")
        scene = json.loads(str(data["scene"]))
        targets = [t for t in scene["targets"] if t.get("enabled", True)]
        if len(targets) != 1 or targets[0].get("realistic_movement", False):
            raise ValueError("Array reference requires one fixed-delay target")
        status = json.loads(str(data["fpga_status"]))
        active = [i for i in range(4) if status["mask"] & (1 << i)]
        if len(active) != 1:
            raise ValueError("Array reference must have one active FPGA path")
        word = status["targets"][active[0]]["phase_increment"]
        doppler = ((word + 2**31) % 2**32 - 2**31) * status["sample_rate_hz"] / 2**32
        if abs(doppler) < 1:
            raise ValueError("Array reference needs a Doppler tag to separate leakage")
        bins = data["bins"]
        size = iq.shape[-1]
        rate = float(data["sample_rate"])
        reference_frequencies = bins * rate / size
        if min(frequencies) < min(reference_frequencies) or max(frequencies) > max(
            reference_frequencies
        ):
            raise ValueError("Array reference does not cover the measurement band")
        pilots = data["reference"][bins % size]
        channel = np.fft.fft(iq, axis=-1)[..., bins % size] / pilots
        direct = np.mean(
            np.fft.fft(data["baseline"], axis=-1)[..., bins % size] / pilots, axis=0
        )
        channel *= direct.conj()[None] / (abs(direct)[None] + 1e-9)
        channel -= channel.mean(axis=0, keepdims=True)
        ticks = (
            np.unwrap(data["ticks"].astype(float) * 2 * np.pi / 2**24)
            * 2**24
            / (2 * np.pi)
        )
        time = (ticks - ticks[0]) * 256 / rate
    window = np.hanning(len(time))
    gain = (
        np.einsum("t,tak->ak", window * np.exp(-2j * np.pi * doppler * time), channel)
        / window.sum()
    )
    anchor = np.argmax(np.sum(abs(gain) ** 2, axis=1))
    order = np.argsort(reference_frequencies)
    cross = gain * gain[anchor].conj()
    if phase_model == "constant":
        phase = np.angle(np.sum(cross[..., order] * np.hanning(len(order)), axis=1))
        return np.broadcast_to(
            np.exp(-1j * phase[:, None]) / np.sqrt(receiver_count),
            (receiver_count, len(frequencies)),
        ).copy()
    phase = np.unwrap(np.angle(cross)[..., order], axis=1)
    return np.array(
        [
            np.exp(-1j * np.interp(frequencies, reference_frequencies[order], row))
            for row in phase
        ]
    ) / np.sqrt(receiver_count)
