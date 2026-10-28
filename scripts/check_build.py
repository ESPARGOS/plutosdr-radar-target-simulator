#!/usr/bin/env python3
"""Verify the source, bitstream and timing-report hashes before deployment."""

from build_provenance import verify

if __name__ == "__main__":
    try:
        manifest = verify()
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(f"Unverified FPGA build: {error}. Run make fpga.")
    print(f"Verified FPGA build from {manifest['built_at']}")
