#!/usr/bin/env python3
"""Build from a clean FPGA project and record its inputs and outputs."""

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
)


def main():
    try:
        verify()
        print("FPGA sources and artifacts match the passing build manifest")
        return
    except (OSError, ValueError, KeyError):
        pass
    before = snapshot()
    manifest_path = ROOT / MANIFEST
    manifest_path.unlink(missing_ok=True)
    tool = subprocess.check_output(["vivado", "-version"], text=True)
    # Do not bless an old bitstream merely because make considered it up to date.
    subprocess.run(["make", "-C", str(ROOT / PROJECT), "clean-all"], check=True)
    subprocess.run(["make", "-C", str(ROOT / PROJECT)], check=True)
    if snapshot() != before:
        raise SystemExit("Sources changed during FPGA build; no manifest was written")
    if PASS_MESSAGE not in (ROOT / TIMING).read_text():
        raise SystemExit("FPGA implementation failed timing; no manifest was written")
    manifest = {
        "schema": 1,
        "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "toolchain": tool.strip(),
        "container_image": os.environ.get("RTS_BUILD_IMAGE", "unknown"),
        "sources": before,
        "artifacts": {str(path): digest(ROOT / path) for path in (BITSTREAM, TIMING)},
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = manifest_path.with_suffix(".json.new")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n")
    temporary.replace(manifest_path)
    verify()
    print(f"Verified build manifest: {manifest_path}")


if __name__ == "__main__":
    main()
