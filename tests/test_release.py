"""Check release integrity and exclusion of local build/device files."""

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "package_release", ROOT / "scripts/package_release.py"
)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTest(unittest.TestCase):
    def test_bundle_and_corrupt_firmware(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "build") as temp:
            root = Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "build").mkdir()
            (root / ".gitignore").write_text(
                "/build/\n/release/\n/private-tests/\n.env\n"
            )
            (root / "README.md").write_text("Current working copy\n")
            (root / ".env").write_text("private settings\n")
            (root / "private-tests").mkdir()
            (root / "private-tests/device.json").write_text("private device record\n")
            firmware = root / "build/firmware"
            firmware.mkdir()
            (firmware / "pluto.frm").write_bytes(b"firmware")
            (firmware / "firmware-manifest.json").write_text(
                json.dumps(
                    {
                        "inputs": {"README.md": release.digest(root / "README.md")},
                        "artifacts": {
                            "pluto.frm": hashlib.sha256(b"firmware").hexdigest()
                        },
                    }
                )
            )
            original = release.ROOT
            release.ROOT = root
            try:
                output = root / "release"
                release.package(firmware, output)
                with tarfile.open(
                    output / "radar-target-simulator-source.tar.gz"
                ) as archive:
                    self.assertEqual(
                        set(archive.getnames()),
                        {
                            "radar-target-simulator/.gitignore",
                            "radar-target-simulator/README.md",
                        },
                    )
                    self.assertEqual(
                        archive.extractfile("radar-target-simulator/README.md").read(),
                        b"Current working copy\n",
                    )
                for line in (output / "SHA256SUMS").read_text().splitlines():
                    digest, name = line.split("  ")
                    self.assertEqual(release.digest(output / name), digest)
                release.package(firmware, output)
                (root / "README.md").write_text("Changed after packaging\n")
                with self.assertRaisesRegex(ValueError, "Source changed"):
                    release.package(firmware, output)
                (root / "README.md").write_text("Current working copy\n")
                (firmware / "pluto.frm").write_bytes(b"corrupt")
                with self.assertRaisesRegex(ValueError, "does not match"):
                    release.package(firmware, output)
                self.assertEqual((output / "pluto.frm").read_bytes(), b"firmware")
            finally:
                release.ROOT = original


if __name__ == "__main__":
    unittest.main()
