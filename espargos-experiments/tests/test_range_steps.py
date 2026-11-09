#!/usr/bin/env python3
"""Check physical units, sweep ordering and empirical percentile aggregation."""
import sys
from pathlib import Path
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from range_steps import C, RATES, positions, summarize


class RangeStepsTest(unittest.TestCase):
    def test_hardware_positions(self):
        for rate in RATES.values():
            offsets = positions(rate, 100, 10)
            np.testing.assert_equal(offsets * 1024, np.round(offsets * 1024))
            ranges = offsets / rate * C * 500
            self.assertLessEqual(abs(ranges[-1] - 100), C * 500 / rate / 2048)
            self.assertTrue(np.all(np.diff(offsets) > 0))

    def test_independent_sweeps_and_references(self):
        records = []
        for repeat in range(10):
            points = [dict(expected_delay_ns=0, measured_delay_ns=0, raw_delay_ns=0)]
            for requested in ([10, 20] if repeat % 2 == 0 else [20, 10]):
                points.append(dict(expected_delay_ns=requested * 2e6 / C,
                                   measured_delay_ns=(requested + repeat) * 2e6 / C))
            points.append(dict(expected_delay_ns=0, measured_delay_ns=0, raw_delay_ns=.1))
            records.append(dict(points=points))
        result = summarize(records)
        np.testing.assert_allclose(result["requested_mm"], [10, 20])
        np.testing.assert_allclose(result["median_mm"], [14.5, 24.5])
        np.testing.assert_allclose(result["p10_mm"], [10.9, 20.9])
        np.testing.assert_allclose(result["p90_mm"], [18.1, 28.1])
        self.assertAlmostEqual(result["maximum_absolute_error_mm"], 9)
        self.assertEqual(result["repeats"], 10)
        with self.assertRaises(ValueError):
            summarize(records[:1])


if __name__ == "__main__":
    unittest.main()
