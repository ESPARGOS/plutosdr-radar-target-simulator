"""Check the delay fit independently of a programmed target range."""

import sys
from pathlib import Path
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from bandwidth_latency import estimate_delay


class LatencyTest(unittest.TestCase):
    def test_wide_and_narrow_bands(self):
        for spacing, count, delay in [(312500, 71, .414), (312500, 71, 1.319),
                                      (9765.625, 8, 3.05)]:
            frequencies = np.r_[np.arange(-count, 0), np.arange(1, count+1)] * spacing
            echo = np.exp(-2j*np.pi*frequencies*delay*1e-6)
            # Independent receive phases must not cancel in the delay estimate.
            response = np.array([1, 1j, -1, -1j])[:, None] * echo
            self.assertAlmostEqual(estimate_delay(frequencies, response), delay, places=6)


if __name__ == "__main__":
    unittest.main()
