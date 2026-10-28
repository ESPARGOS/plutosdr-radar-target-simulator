import argparse, sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))
from scene import validate
from control import Controller


class ControlTests(unittest.TestCase):
    def test_quantization(self):
        t = validate(
            {
                "targets": [
                    dict(delay_us=1.023, doppler_hz=-17.7, gain_db=-6, enabled=True)
                ]
            },
            20e6,
        )[0]
        self.assertEqual(t["delay_samples"], 20)
        self.assertLess(abs(t["doppler_hz"] + 17.7), 20e6 / 2**32 / 2)

    def test_reject_invalid(self):
        base = dict(delay_us=1, doppler_hz=1, gain_db=-6, enabled=True)
        for key, value in [
            ("delay_us", -1),
            ("delay_us", 103),
            ("doppler_hz", float("nan")),
            ("doppler_hz", 10e6),
            ("gain_db", 1),
            ("enabled", "yes"),
        ]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate({"targets": [{**base, key: value}]}, 20e6)
        with self.assertRaises(ValueError):
            validate({"targets": [base] * 5}, 20e6)

    def test_demo_mute(self):
        c = Controller(
            argparse.Namespace(
                demo=True, pluto="192.168.4.1", sample_rate=20e6, frequency=2380e6
            )
        )
        c.apply({"targets": [dict(delay_us=1, doppler_hz=10, gain_db=-10)]})
        self.assertTrue(c.state()["targets"][0]["enabled"])
        c.mute()
        self.assertFalse(c.state()["targets"][0]["enabled"])


if __name__ == "__main__":
    unittest.main()
