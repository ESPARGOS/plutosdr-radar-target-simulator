#!/usr/bin/env python3
"""Compare the shared standard-mode datapath against exact integer arithmetic."""

from pathlib import Path
import numpy as np
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from generate_standard_filters import halfband, fractional

r = Path("build/tests/standard")
r.mkdir(parents=True, exist_ok=True)
h = halfband()[::2]
f = fractional()
rng = np.random.default_rng(4)
osc = np.empty((2, 4, 1024, 2), dtype=np.int64)
for bank in range(2):
    for target in range(4):
        angle = 2 * np.pi * np.arange(1024) / 1024
        gain = [1, 0.5, 0.25, 0.125][(target + bank) % 4]
        osc[bank, target, :, 0] = np.rint(32767 * gain * np.cos(angle))
        osc[bank, target, :, 1] = np.rint(32767 * gain * np.sin(angle))
(r / "oscillator.hex").write_text(
    "".join(
        f"{(int(v[0])&65535)|((int(v[1])&65535)<<16):08x}\n" for v in osc.reshape(-1, 2)
    )
)
history = np.zeros((48, 2), dtype=np.int64)
virtual = []
expected = {}
rows = []
last_bank = None
sticky_clip = False


def pack(values, bits):
    return sum(int(v) << (k * bits) for k, v in enumerate(values))


for n in range(70000):
    valid = n >= 4 and n % 4 == 0
    x = rng.integers(-2048, 2048, size=2)
    delays = rng.integers(0, 12277, size=4)
    if n % 32 == 0:
        delays[:] = rng.choice([0, 1, 2, 3, 7, 8, 12276])
    fractions = rng.integers(1024, size=4)
    phases = (n * np.array([3, 7, 13, 19])) % 1024
    enabled = int(rng.integers(16))
    bank = (n // 1200) % 2
    if valid:
        history[1:] = history[:-1]
        history[0] = x
        pos = len(virtual)
        virtual.append(((history.T @ h + 16384) >> 15).copy())
        virtual.append(history[23].copy() * 4)
        echoes = []
        for target in range(4):
            m = int(2 * delays[target] + (fractions[target] >> 9))
            mu = int((fractions[target] & 511) * 2)
            taps = np.array(
                [virtual[pos - m - k] if pos - m - k >= 0 else [0, 0] for k in range(8)]
            )
            di, dq = (taps.T @ f[mu] + 8192) >> 14
            if not (enabled & (1 << target)):
                di = dq = 0
            c, s = osc[bank, target, phases[target]]
            echoes.append([(di * c - dq * s) >> 15, (di * s + dq * c) >> 15])
        total = np.sum(echoes, axis=0)
        overflow = bool(np.any((total < -32768) | (total > 32767)))
        sticky_clip = overflow if bank != last_bank else sticky_clip or overflow
        last_bank = bank
        expected[n + 33] = (np.clip(total, -32768, 32767), bank, sticky_clip)
    rows.append(
        f"{int(valid)} {pack(x&4095,12):06x} {pack(delays,14):014x} {pack(fractions,10):010x} {pack(phases,10):010x} {enabled:x} {bank}\n"
    )
(r / "target-stimulus.txt").write_text("".join(rows))
(r / "tb_targets.sv").write_text("""module tb;
reg clk=0;always #5 clk=~clk;
wire table_clk=clk;
reg reset=1,valid=0,active_table=0,muted=0,table_write=0;
reg [23:0] sample=0;
reg [55:0] delays=0;
reg [39:0] fractions=0,phases=0;
reg [3:0] enabled=0;
reg [12:0] table_address=0;
reg [31:0] table_data=0;
reg [31:0] oscillator[0:8191];
wire [15:0] out_i,out_q;
wire out_valid,out_table,clipped;
standard_targets dut(.*);
integer n,f,code;
initial begin
 $readmemh("build/tests/standard/oscillator.hex",oscillator);
 for(n=0;n<8192;n=n+1) begin
  @(negedge clk);table_write=1;table_address=n;table_data=oscillator[n];
 end
 @(negedge clk);table_write=0;
 f=$fopen("build/tests/standard/target-stimulus.txt","r");
 for(n=0;n<70034;n=n+1) begin
  @(negedge clk);reset=n<2;
  if(n<70000) code=$fscanf(f,"%d %h %h %h %h %h %d\\n",valid,sample,delays,fractions,phases,enabled,active_table); else valid=0;
  @(posedge clk);#1;
  if(out_valid) $display("%0d %h %h %0d %0d",n,out_i,out_q,out_table,clipped);
 end
 $finish;
end
endmodule
""")
sources = [
    str(Path("rtl") / ("standard_" + name + ".sv"))
    for name in ("upsample", "history", "fir", "targets")
] + [str(r / "tb_targets.sv")]
subprocess.run(
    ["iverilog", "-g2012", "-s", "tb", "-o", str(r / "target-sim"), *sources],
    check=True,
)
out = subprocess.check_output(["vvp", str(r / "target-sim")], text=True)
actual = {}
for line in out.splitlines():
    if "$finish" in line:
        continue
    fields = line.split()
    n = int(fields[0])
    a = [int(v, 16) for v in fields[1:3]]
    a = [v - 65536 if v & 32768 else v for v in a]
    actual[n] = (a, int(fields[3]), bool(int(fields[4])))
assert actual.keys() == expected.keys(), (
    list(actual)[:8],
    list(expected)[:8],
    len(actual),
    len(expected),
)
for n, (wanted, bank, clip) in expected.items():
    np.testing.assert_array_equal(actual[n][0], wanted, err_msg=f"clock {n}")
    assert actual[n][1] == bank
    assert actual[n][2] == clip, (n, actual[n][2], clip)
print(
    f"PASS: {len(actual)} four-target scenes, full-range fractional delay, independent phases/gains/enables, table swaps, clipping, startup and history wraparound"
)

# Exercise the sample/core clock crossing with several relative phases.
for offset in (0, 3, 7):
    subprocess.run(
        [
            "iverilog",
            "-g2012",
            "-s",
            "tb",
            f"-Ptb.CORE_OFFSET={offset}",
            "-o",
            str(r / "bank-sim"),
            *sources[:-1],
            "rtl/standard_bank.sv",
            "rtl/target_motion.sv",
            "rtl/nco_rom.v",
            "tests/tb_standard_bank.sv",
        ],
        check=True,
    )
    subprocess.run(["vvp", str(r / "bank-sim")], check=True)
