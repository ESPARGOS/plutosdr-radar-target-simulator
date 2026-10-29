"""Startup must never publish a reduced-rate simulator after calibration fails."""

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StartupTests(unittest.TestCase):
    def run_startup(self, setup_status, calibration_status, motion_status=0):
        (ROOT / "build/tests").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "build/tests") as directory:
            root = Path(directory)
            for name in ("tmp", "usr/bin", "usr/share/radar-web"):
                (root / name).mkdir(parents=True)
            for name, status in {
                "rtsctl": 0,
                "radar.cgi": 0,
                "radar-radio-setup": setup_status,
                "radar-radio-fast": calibration_status,
            }.items():
                path = root / "usr/bin" / name
                path.write_text(f"#!/bin/sh\nexit {status}\n")
                path.chmod(0o755)
            motion = root / "usr/bin/radar-motion"
            motion.write_text(
                f"#!/bin/sh\nexit {motion_status}\n"
                if motion_status
                else f"#!/bin/sh\ntouch {root}/tmp/radar-motion.ready\n"
            )
            motion.chmod(0o755)
            (root / "usr/share/radar-web/index.html").write_text("Test UI")
            # A restart must discard stale readiness and failure markers.
            (root / "tmp/radar-loaded").touch()
            (root / "tmp/radar-failed").touch()
            (root / "tmp/radar-motion.ready").touch()
            # Substitute paths once, keeping every test artifact out of /tmp.
            source = re.sub(
                r"/(?:usr/share/radar-web|usr/bin|www|tmp)(?=/|\s|$)",
                lambda match: str(root) + match.group(0),
                (ROOT / "host/S61radar").read_text(),
            )
            script = root / "startup.sh"
            script.write_text(source)
            result = subprocess.run(["sh", str(script), "start"], capture_output=True)
            self.assertTrue((root / "www/index.html").exists())
            if setup_status or calibration_status or motion_status:
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((root / "tmp/radar-loaded").exists())
                self.assertTrue((root / "tmp/radar-failed").exists())
            else:
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue((root / "tmp/radar-loaded").exists())
                self.assertFalse((root / "tmp/radar-failed").exists())

    def test_radio_setup_failure(self):
        self.run_startup(1, 0)

    def test_calibration_failure(self):
        self.run_startup(0, 1)

    def test_recovery_failure(self):
        self.run_startup(0, 2)

    def test_motion_start_failure(self):
        self.run_startup(0, 0, 1)

    def test_success(self):
        self.run_startup(0, 0)


if __name__ == "__main__":
    unittest.main()
