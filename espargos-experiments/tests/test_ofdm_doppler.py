#!/usr/bin/env python3
"""Recover independent subcarrier Dopplers without imposing the predicted slope."""
import sys
from pathlib import Path
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ofdm_doppler import estimate


class DopplerTest(unittest.TestCase):
    def test_frequency_dependence_and_fixed_delay(self):
        rng = np.random.default_rng(308)
        t = np.arange(0, 14, 1/150)
        t += rng.uniform(-.0001, .0001, len(t))
        t = np.delete(t, [127, 802])
        t[[41, 42]] = t[[42, 41]]
        frequency = np.r_[np.linspace(-27.5e6, -1e6, 16), np.linspace(1e6, 27.5e6, 16)]
        gains = rng.normal(size=(4, len(frequency))) + 1j*rng.normal(size=(4, len(frequency)))
        for moving in [False, True]:
            # Add a non-linear frequency dependence unknown to the estimator.
            extra = .03 * np.cos(frequency / 9e6) if moving else 0
            expected = 40 + .12 + (40 * frequency / 2385e6 if moving else 0) + extra
            expected = np.broadcast_to(expected, frequency.shape)
            echo = np.exp(2j*np.pi*t[:, None]*expected)
            # One subcarrier briefly fades into noise. Its phase cannot safely
            # be unwrapped through that interval, but the tone is identifiable.
            echo[(t > 6) & (t < 8), 0] *= .001
            channel = echo[:, None, :] * gains[None] + 30*(1+.2j)
            channel += .02*(rng.normal(size=channel.shape)+1j*rng.normal(size=channel.shape))
            measured, quality = estimate(t, channel, 40)
            np.testing.assert_allclose(measured, expected, atol=.001)
            self.assertGreater(min(quality['spatial_coherence']), .98)
        with self.assertRaises(ValueError):
            estimate(t, channel, 74)


if __name__ == '__main__':
    unittest.main()
