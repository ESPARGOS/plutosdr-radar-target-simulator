"""Tie a bitstream and timing report to the sources that produced them."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = Path("vendor/adi-hdl/projects/pluto")
BITSTREAM = PROJECT / "pluto.runs/impl_1/system_top.bit"
TIMING = PROJECT / "timing_impl.log"
MANIFEST = Path("build/fpga-manifest.json")
PASS_MESSAGE = "All user specified timing constraints are met."


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_paths(root):
    files = {
        Path("scripts") / name
        for name in (
            "prepare_hdl.py",
            "generate_rom.py",
            "bootstrap_hdl.sh",
            "container.sh",
            "build_fpga.py",
            "build_provenance.py",
        )
    }
    for directory in ("rtl", "patches"):
        files.update(
            path.relative_to(root)
            for path in (root / directory).rglob("*")
            if path.is_file()
        )
    vendor = Path("vendor/adi-hdl")
    inventory = vendor / ".radar-source-files.json"
    files.add(inventory)
    for name in json.loads((root / inventory).read_text()):
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Invalid vendor source inventory")
        files.add(vendor / relative)
    files.update(
        path.relative_to(root)
        for path in (root / vendor / "library/radar_axi").iterdir()
        if path.is_file() and path.suffix in (".v", ".sv", ".xdc", ".tcl")
    )
    files.add(vendor / "library/radar_axi/Makefile")
    return sorted(files)


def snapshot(root=ROOT):
    return {str(path): digest(root / path) for path in source_paths(root)}


def verify(root=ROOT):
    manifest = json.loads((root / MANIFEST).read_text())
    if manifest.get("schema") != 1:
        raise ValueError("Unsupported FPGA manifest")
    current = snapshot(root)
    if current != manifest["sources"]:
        changed = sorted(
            path
            for path in current.keys() | manifest["sources"].keys()
            if current.get(path) != manifest["sources"].get(path)
        )
        raise ValueError(
            "FPGA sources changed; run make fpga: " + ", ".join(changed[:8])
        )
    for path in (BITSTREAM, TIMING):
        if digest(root / path) != manifest["artifacts"].get(str(path)):
            raise ValueError(f"FPGA artifact changed since build: {path}")
    if PASS_MESSAGE not in (root / TIMING).read_text():
        raise ValueError("FPGA implementation failed timing")
    return manifest
