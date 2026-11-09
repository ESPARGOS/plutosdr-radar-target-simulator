#!/usr/bin/env python3
"""Build from a clean FPGA project and record its inputs and outputs."""

import argparse
import datetime
import json
import os
import subprocess
from build_provenance import (
    ROOT,
    PROJECT,
    BITSTREAM,
    TIMING,
    MANIFEST,
    PASS_MESSAGE,
    digest,
    snapshot,
    verify,
    layout,
)


def build(mode):
    _, project, bitstream, timing, manifest_file = layout(mode)
    try:
        verify(mode=mode)
        print("FPGA sources and artifacts match the passing build manifest")
        return
    except (OSError, ValueError, KeyError):
        pass
    before = snapshot(mode=mode)
    manifest_path = ROOT / manifest_file
    manifest_path.unlink(missing_ok=True)
    tool = subprocess.check_output(["vivado", "-version"], text=True)
    # Do not bless an old bitstream merely because make considered it up to date.
    subprocess.run(["make", "-C", str(ROOT / project), "clean-all"], check=True)
    subprocess.run(["make", "-C", str(ROOT / project)], check=True)
    if snapshot(mode=mode) != before:
        raise SystemExit("Sources changed during FPGA build; no manifest was written")
    if PASS_MESSAGE not in (ROOT / timing).read_text():
        raise SystemExit("FPGA implementation failed timing; no manifest was written")
    manifest = {
        "schema": 1,
        "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "toolchain": tool.strip(),
        "container_image": os.environ.get("RTS_BUILD_IMAGE", "unknown"),
        "sources": before,
        "artifacts": {str(path): digest(ROOT / path) for path in (bitstream, timing)},
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = manifest_path.with_suffix(".json.new")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n")
    temporary.replace(manifest_path)
    verify(mode=mode)
    print(f"Verified build manifest: {manifest_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("standard", "overclocked", "both"), default="both")
    mode = parser.parse_args().mode
    for selected in (("standard", "overclocked") if mode == "both" else (mode,)):
        build(selected)
