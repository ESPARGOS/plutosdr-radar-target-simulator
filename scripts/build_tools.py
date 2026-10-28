#!/usr/bin/env python3
"""Build the ARM tools and record their sources, compiler and binary hashes."""

import argparse
import json
import subprocess
from pathlib import Path

from build_provenance import digest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "build/tools-manifest.json"
COMPILER = "/opt/Xilinx/Vitis/2023.2/gnu/aarch32/lin/gcc-arm-linux-gnueabi/bin/arm-linux-gnueabihf-gcc"
COMMON = ["host/radar_control.c", "host/radar_linux.c"]
PROGRAMS = {
    "rtsctl": ["host/rtsctl.c", *COMMON],
    "radar.cgi": ["host/radar_cgi.c", *COMMON],
    "radio-pn": ["host/radio_pn.c"],
}


def sources():
    paths = {path for files in PROGRAMS.values() for path in files}
    paths.update(
        [
            "host/radar_control.h",
            "host/radar_linux.h",
            "scripts/build_tools.py",
            "scripts/container.sh",
        ]
    )
    return {path: digest(ROOT / path) for path in sorted(paths)}


def verify():
    manifest = json.loads(MANIFEST.read_text())
    if manifest.get("schema") != 1 or manifest["sources"] != sources():
        raise ValueError("Native tool sources changed; run make tools")
    for name in PROGRAMS:
        if manifest["artifacts"].get(name) != digest(ROOT / "build" / name):
            raise ValueError(f"Native tool changed: {name}; run make tools")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify existing binaries without rebuilding",
    )
    if parser.parse_args().check:
        verify()
        print("Native tools match their build manifest")
        return
    ROOT.joinpath("build").mkdir(exist_ok=True)
    before = sources()
    MANIFEST.unlink(missing_ok=True)
    container = [str(ROOT / "scripts/container.sh")]
    image = subprocess.check_output(
        [*container, "printenv", "RTS_BUILD_IMAGE"], cwd=ROOT, text=True
    ).strip()
    compiler = subprocess.check_output(
        [*container, COMPILER, "--version"], cwd=ROOT, text=True
    )
    for name, files in PROGRAMS.items():
        subprocess.run(
            [
                *container,
                COMPILER,
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-static",
                "-o",
                f"build/{name}",
                *files,
                "-lm",
            ],
            cwd=ROOT,
            check=True,
        )
    if sources() != before:
        raise RuntimeError("Native sources changed during compilation")
    manifest = {
        "schema": 1,
        "compiler": compiler.strip(),
        "container_image": image,
        "sources": before,
        "artifacts": {name: digest(ROOT / "build" / name) for name in PROGRAMS},
    }
    temporary = MANIFEST.with_suffix(".json.new")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n")
    temporary.replace(MANIFEST)
    verify()


if __name__ == "__main__":
    main()
