"""Reject stale FPGA sources, substituted artifacts and missing build records."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_provenance as provenance


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "build/tests").mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=ROOT / "build/tests")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for directory in [
            "scripts",
            "rtl",
            "patches",
            "build",
            "vendor/adi-hdl/library/radar_axi",
        ]:
            (self.root / directory).mkdir(parents=True)
        for name in [
            "prepare_hdl.py",
            "generate_rom.py",
            "bootstrap_hdl.sh",
            "container.sh",
            "build_fpga.py",
            "build_provenance.py",
        ]:
            (self.root / "scripts" / name).write_text("source")
        (self.root / "rtl/target_bank.sv").write_text("RTL")
        (self.root / "vendor/adi-hdl/.radar-source-files.json").write_text("[]")
        (self.root / "vendor/adi-hdl/library/radar_axi/Makefile").write_text("build")
        for path, data in [
            (provenance.BITSTREAM, "bitstream"),
            (provenance.TIMING, provenance.PASS_MESSAGE),
        ]:
            (self.root / path).parent.mkdir(parents=True, exist_ok=True)
            (self.root / path).write_text(data)
        manifest = {
            "schema": 1,
            "sources": provenance.snapshot(self.root),
            "artifacts": {
                str(path): provenance.digest(self.root / path)
                for path in [provenance.BITSTREAM, provenance.TIMING]
            },
        }
        (self.root / provenance.MANIFEST).write_text(json.dumps(manifest))

    def test_matching_build(self):
        provenance.verify(self.root)

    def test_changed_and_added_source(self):
        for path in ["rtl/target_bank.sv", "rtl/new.sv"]:
            with self.subTest(path=path):
                original = (
                    (self.root / path).read_bytes()
                    if (self.root / path).exists()
                    else None
                )
                (self.root / path).write_text("changed")
                with self.assertRaisesRegex(ValueError, "sources changed"):
                    provenance.verify(self.root)
                if original is None:
                    (self.root / path).unlink()
                else:
                    (self.root / path).write_bytes(original)

    def test_replaced_artifacts(self):
        for path in [provenance.BITSTREAM, provenance.TIMING]:
            with self.subTest(path=path):
                original = (self.root / path).read_bytes()
                (self.root / path).write_text("replacement")
                with self.assertRaisesRegex(ValueError, "artifact changed"):
                    provenance.verify(self.root)
                (self.root / path).write_bytes(original)

    def test_missing_manifest(self):
        (self.root / provenance.MANIFEST).unlink()
        with self.assertRaises(FileNotFoundError):
            provenance.verify(self.root)


if __name__ == "__main__":
    unittest.main()
