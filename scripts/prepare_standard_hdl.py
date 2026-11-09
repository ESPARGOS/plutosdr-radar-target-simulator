#!/usr/bin/env python3
"""Prepare a separate standard-rate FPGA project from the patched ADI sources."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "vendor/adi-hdl"
DESTINATION = ROOT / "build/standard-hdl"


def write(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_bytes() != contents:
        path.write_bytes(contents)


def main():
    inventory = ".radar-source-files.json"
    names = json.loads((SOURCE / inventory).read_text()) + [inventory]
    names += [str(path.relative_to(SOURCE))
              for path in (SOURCE / "library/radar_axi").iterdir()
              if path.suffix in (".v", ".sv", ".tcl", ".xdc") or path.name == "Makefile"]
    extra = "standard_upsample.sv standard_history.sv standard_fir.sv standard_targets.sv standard_bank.sv standard_clock.sv"
    for name in names:
        contents = (SOURCE / name).read_bytes()
        if name == "library/radar_axi/radar_axi.sv":
            contents = contents.replace(b"target_bank bank(", b"standard_clock bank(")
            contents = contents.replace(b"32'h00020002", b"32'h00020003")
        elif name == "library/radar_axi/Makefile":
            contents = contents.replace(b"GENERIC_DEPS +=", b"GENERIC_DEPS += " + extra.encode())
        elif name == "library/radar_axi/radar_axi_ip.tcl":
            contents = contents.replace(b"radar_cdc.xdc]", b"radar_cdc.xdc " + extra.encode() + b"]")
        elif name == "library/axi_ad9361/xilinx/axi_ad9361_cmos_if.v":
            # The normal interface clock needs no overclocked clock conditioner.
            contents = contents.replace(b".RADAR_CLOCK_CLEANER (RADAR_LOW_LATENCY)",
                                        b".RADAR_CLOCK_CLEANER (0)")
        elif name == "projects/pluto/system_constr.xdc":
            text = contents.decode().replace("-period  6.24", "-period  16.276042")
            start = text.index("# Raw and conditioned clocks")
            end = text.index("# Improve source-synchronous", start)
            text = text[:start] + text[end:]
            text = text.replace("# Extra margin for the experimental overclocked source.",
                                "# Timing margin for the standard interface clock.")
            contents = text.replace("-setup 0.750", "-setup 0.150").replace("-hold 0.150", "-hold 0.050").encode()
        write(DESTINATION / name, contents)


if __name__ == "__main__":
    main()
