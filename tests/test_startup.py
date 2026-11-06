"""Only a validated fast or fallback profile may publish a ready simulator."""

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StartupTests(unittest.TestCase):
    def run_startup(self, setup_status, calibration_status, standard_status=0, mode="overclocked", reconfigure=False):
        (ROOT / "build/tests").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "build/tests") as directory:
            root = Path(directory)
            for name in ("tmp", "usr/bin", "usr/share/radar-web", "mnt/jffs2"):
                (root / name).mkdir(parents=True)
            (root / "mnt/jffs2/radar-mode").write_text(mode + "\n")
            phy = root / "sys/bus/iio/devices/iio:device0"
            phy.mkdir(parents=True)
            for name, value in {"name": "ad9361-phy", "out_altvoltage0_RX_LO_frequency": "2385000000",
                                "in_voltage0_hardwaregain": "31.000000 dB",
                                "out_voltage0_hardwaregain": "-27.000000 dB"}.items():
                (phy / name).write_text(value + "\n")
            for name, status in {
                "rtsctl": 0,
                "radar.cgi": 0,
                "radar-radio-setup": setup_status,
            }.items():
                path = root / "usr/bin" / name
                path.write_text(f"#!/bin/sh\nexit {status}\n")
                path.chmod(0o755)
            (root / "tmp/rtsctl").write_bytes((root / "usr/bin/rtsctl").read_bytes())
            (root / "tmp/rtsctl").chmod(0o755)
            fast = root / "usr/bin/radar-radio-fast"
            fast.write_text(
                f'#!/bin/sh\nif [ "$1" = 61440000 ]; then exit {standard_status}; fi\nexit {calibration_status}\n'
            )
            fast.chmod(0o755)
            (root / "usr/share/radar-web/index.html").write_text("Test UI")
            # A restart must discard stale readiness and failure markers.
            (root / "tmp/radar-loaded").touch()
            (root / "tmp/radar-failed").touch()
            (root / "tmp/radar-fallback").touch()
            # Substitute paths once, keeping every test artifact out of /tmp.
            source = re.sub(
                r"/(?:usr/share/radar-web|usr/bin|www|tmp|mnt/jffs2|sys/bus/iio/devices)(?=/|\s|$)",
                lambda match: str(root) + match.group(0),
                (ROOT / "host/S61radar").read_text(),
            )
            script = root / "startup.sh"
            script.write_text(source)
            result = subprocess.run(["sh", str(script), "reconfigure" if reconfigure else "start"], capture_output=True)
            self.assertTrue((root / "www/index.html").exists())
            started, changed, stage = (
                (root / "tmp/radar-startup-state").read_text().split()
            )
            self.assertGreaterEqual(float(changed), float(started))
            self.assertEqual(
                stage,
                (
                    "radio"
                    if setup_status
                    else (
                        ("standard" if mode == "standard" else "fallback")
                        if standard_status and (mode == "standard" or calibration_status)
                        else "ready"
                    )
                ),
            )
            self.assertEqual(
                (root / "tmp/radar-fallback").exists(),
                not setup_status and mode != "standard" and bool(calibration_status),
            )
            if setup_status or (standard_status and (mode == "standard" or calibration_status)):
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((root / "tmp/radar-loaded").exists())
                self.assertTrue((root / "tmp/radar-failed").exists())
            else:
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue((root / "tmp/radar-loaded").exists())
                self.assertFalse((root / "tmp/radar-failed").exists())
                if reconfigure:
                    self.assertEqual((phy / "in_voltage0_hardwaregain").read_text().strip(), "31.000000")
                    self.assertEqual((phy / "out_voltage0_hardwaregain").read_text().strip(), "-27.000000")
                    self.assertEqual((phy / "out_altvoltage1_TX_LO_frequency").read_text().strip(), "2385000000")

    def test_radio_setup_failure(self):
        self.run_startup(1, 0)

    def test_fallback_after_calibration_failure(self):
        self.run_startup(0, 1)

    def test_fallback_after_fast_recovery_failure(self):
        self.run_startup(0, 2)

    def test_both_profiles_fail(self):
        self.run_startup(0, 1, standard_status=1)

    def test_explicit_standard_skips_overclocked_setup(self):
        self.run_startup(0, 99, mode="standard")

    def test_explicit_standard_failure_stays_muted(self):
        self.run_startup(0, 0, standard_status=1, mode="standard")

    def test_reconfigure_preserves_carrier_and_numeric_gains(self):
        self.run_startup(0, 0, mode="standard", reconfigure=True)

    def test_success(self):
        self.run_startup(0, 0)


if __name__ == "__main__":
    unittest.main()
