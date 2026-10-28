#!/usr/bin/env python3
"""Check that the bitstream exists and passed the final timing report."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
project=root/'vendor/adi-hdl/projects/pluto'
report=project/'timing_impl.log'
bit=project/'pluto.runs/impl_1/system_top.bit'
if not bit.exists() or not report.exists():raise SystemExit('Missing bitstream or final timing report; run make fpga')
text=report.read_text()
if 'All user specified timing constraints are met.' not in text:
    raise SystemExit('FPGA implementation did not meet timing; refusing deployment')
print(f'Timing passed: {report}')
