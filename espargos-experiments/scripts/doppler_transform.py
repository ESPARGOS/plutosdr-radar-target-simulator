"""Doppler matched filtering with recorded snapshot timestamps."""

import numpy as np
from scipy.signal import ZoomFFT


def doppler_response(samples, time, frequencies):
    """Apply a Hann window and evaluate the requested uniform frequency grid.

    Regular snapshots use a chirp-z transform. Missing or irregular snapshots
    use their actual timestamps, in batches that bound temporary memory use.
    """
    time = np.asarray(time) - time[0]
    window = np.hanning(len(time))
    spacing = np.median(np.diff(time))
    weighted = samples * window.reshape((-1,) + (1,) * (samples.ndim - 1))
    regular_time = np.allclose(np.diff(time), spacing, rtol=1e-6, atol=1e-12)
    regular_grid = len(frequencies) > 1 and np.allclose(
        np.diff(frequencies), frequencies[1] - frequencies[0], rtol=1e-10, atol=1e-12
    )
    if regular_time and regular_grid:
        transform = ZoomFFT(
            len(time),
            [frequencies[0], frequencies[-1]],
            m=len(frequencies),
            fs=1 / spacing,
            endpoint=True,
        )
        return transform(weighted, axis=0) / window.sum()
    result = np.empty((len(frequencies),) + samples.shape[1:], complex)
    flattened = weighted.reshape(len(time), -1)
    for start in range(0, len(frequencies), 128):
        stop = min(start + 128, len(frequencies))
        matched = np.exp(-2j * np.pi * frequencies[start:stop, None] * time[None])
        result[start:stop] = (matched @ flattened).reshape(result[start:stop].shape)
    return result / window.sum()
