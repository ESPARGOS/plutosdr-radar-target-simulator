#!/usr/bin/env python3
"""Collect firmware, provenance, project sources and checksums for GitHub Releases."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package(firmware, output):
    manifest = json.loads((firmware / "firmware-manifest.json").read_text())
    if digest(firmware / "pluto.frm") != manifest["artifacts"]["pluto.frm"]:
        raise ValueError("Firmware does not match its build manifest")
    for sources in (
        manifest.get("inputs", {}),
        manifest.get("native", {}).get("sources", {}),
        manifest.get("fpga", {}).get("sources", {}),
    ):
        for name, expected in sources.items():
            if name == "base_firmware":
                continue
            path = ROOT / name
            if not path.is_file() or digest(path) != expected:
                raise ValueError(f"Source changed since firmware packaging: {name}")
    # Include current edits and new, non-ignored files, rather than an older commit.
    paths = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT,
        )
        .decode()
        .split("\0")
    )
    paths = sorted({p for p in paths if p and (ROOT / p).is_file()})
    if output.exists() and any(output.iterdir()):
        expected = {
            "pluto.frm",
            "firmware-manifest.json",
            "radar-target-simulator-source.tar.gz",
            "SHA256SUMS",
        }
        unexpected = {p.name for p in output.iterdir()} - expected
        if unexpected:
            raise ValueError(
                f"Refusing to overwrite unrelated release files: {sorted(unexpected)}"
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="release-", dir=ROOT / "build") as temp:
        stage = Path(temp)
        for name in ("pluto.frm", "firmware-manifest.json"):
            shutil.copyfile(firmware / name, stage / name)
        with tarfile.open(
            stage / "radar-target-simulator-source.tar.gz", "w:gz"
        ) as archive:
            for name in paths:
                archive.add(
                    ROOT / name,
                    arcname="radar-target-simulator/" + name,
                    recursive=False,
                )
        sums = [f"{digest(p)}  {p.name}\n" for p in sorted(stage.iterdir())]
        (stage / "SHA256SUMS").write_text("".join(sums))
        output.mkdir(exist_ok=True)
        for path in stage.iterdir():
            shutil.copyfile(path, output / path.name)
    print(f"Upload all four files in {output} to the GitHub release.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--firmware-dir", type=Path, default=ROOT / "build/release-firmware"
    )
    args = parser.parse_args()
    package(args.firmware_dir.resolve(), ROOT / "release")


if __name__ == "__main__":
    main()
