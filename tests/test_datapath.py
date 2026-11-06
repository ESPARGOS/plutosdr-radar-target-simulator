#!/usr/bin/env python3
"""Bit-exact oracle: random IQ, signed Doppler, independent delays, wrap, clipping,
configuration changes, phase continuity, startup and sample-clock gaps."""

import math, random, subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
build = root / "build/tests"
build.mkdir(parents=True, exist_ok=True)
rng = random.Random(42)
rows = []
for c in range(180000):
    reset = int(c < 3 or 6500 <= c < 6503)
    configure = int(c in (3, 1501, 3101, 3501, 6001, 6503, 9401, 11001, 12501))
    restart = int(c in (3, 6503, 11001))
    valid = int(
        (c % 2 == 0 or 5000 < c < 5800 or c in (3501, 6001, 9401, 12501))
        and c not in (6002, 6504)
    )
    ds = [0, 1, 17, 2047] if c < 3101 else [3, 9, 100, 1025]
    if c >= 9401:
        ds = [0, 0, 0, 0]
    if c >= 15000:
        ds = [0, 1, 4095, 12275]
        configure = int(c in (15001, 60001, 90001, 120001, 125001, 150001))
    inc = [0, 2**28, (-(2**27)) & 0xFFFFFFFF, 0xFFFFFFFF]
    if c >= 6001:
        inc = [(-(2**29)) & 0xFFFFFFFF, 0, 98765, 2**28]
    mask = 15 if c < 11001 or c >= 12501 else 0
    gain = [8192, 12000, 16384, 4000] if c < 9401 else [32767] * 4
    if 1501 <= c < 3101:
        gain = [0, 1, 32767, 32766]
    if 60000 <= c < 90000:
        ds = [3, 8, 700, 4096]
        gain = [12000, 16384, 32700, 8000]
        inc = [0x12345678, 0xFFEDCBA9, 400, 0]
    if c >= 150000:
        ds = [0, 1, 17, 12275]
        gain = [0, 1, 32766, 32767]
    if 120000 <= c < 125000:
        mask = 0
    iq = [rng.randrange(-2048, 2048) * 16, rng.randrange(-2048, 2048) * 16]
    moving = 5 if c >= 150000 else 0
    steps = [round(0.007 * 2**48), 0, -round(0.013 * 2**48), 0]
    upper = 32 if moving else 12276
    rows.append(
        [
            reset,
            configure,
            restart,
            valid,
            *iq,
            mask,
            *ds,
            *inc,
            *gain,
            moving,
            *steps,
            upper,
        ]
    )
with (build / "stimulus.txt").open("w") as f:
    for row in rows:
        f.write(" ".join(map(str, row)) + "\n")
subprocess.run(
    [
        "iverilog",
        "-g2012",
        "-s",
        "tb",
        "-o",
        str(build / "tb"),
        str(root / "rtl/target_bank.sv"),
        str(root / "rtl/fractional_delay.sv"),
        str(root / "rtl/fractional_rom.sv"),
        str(root / "rtl/target_motion.sv"),
        str(root / "rtl/nco_rom.v"),
        str(root / "tests/tb_bank.sv"),
    ],
    check=True,
)
subprocess.run(["vvp", str(build / "tb")], cwd=build, check=True)
actual = [
    list(map(int, x.split())) for x in (build / "output.txt").read_text().splitlines()
]
assert len(actual) == len(rows), (len(actual), len(rows))
history = []
phases = [0] * 4
pending = {}
held = (0, 0)
clipped = 0
checks = 0
ready_at = 10**9
commit_at = None
active = (0, [0] * 4, [0] * 4, [0] * 4)
clip_pending = 0
positions = [0] * 4
motion_steps = [0] * 4
moving_mask = 0
motion_upper = 12276 << 48
motion_resume_at = 0
import sys

sys.path.insert(0, str(root / "scripts"))
from generate_fractional_rom import coefficients as filter_coefficients

coefficients = [filter_coefficients(i) for i in range(1024)]
for c, (row, out) in enumerate(zip(rows, actual)):
    reset, configure, restart, valid, ii, qq, mask, *params = row
    if reset:
        motion_resume_at = 0
        positions = [0] * 4
        motion_steps = [0] * 4
        moving_mask = 0
        history = []
        phases = [0] * 4
        pending = {}
        held = (0, 0)
        clipped = 0
        ov = 0
        ready_at = 10**9
        commit_at = None
        active = (0, [0] * 4, [0] * 4, [0] * 4)
        clip_pending = 0
    else:
        clipped |= clip_pending
        clip_pending = 0
        ov = int(c in pending)
        if ov:
            value = pending.pop(c)
            clip_pending = int(any(x < -32768 or x > 32767 for x in value))
            held = tuple(max(-32768, min(32767, x)) for x in value)
        advanced = valid and c >= motion_resume_at
        if valid:
            enabled, ds, incs, gains = active
            sums = [0, 0]
            for t in range(4):
                ds[t] = positions[t] >> 48
                coeff = coefficients[(positions[t] >> 38) & 1023]
                samples = [
                    (
                        history[-(ds[t] + k)]
                        if ds[t] + k > 0 and len(history) >= ds[t] + k
                        else ((ii, qq) if ds[t] + k == 0 else (0, 0))
                    )
                    for k in range(8)
                ]
                x, y = [
                    (
                        sum(sample[channel] * co for sample, co in zip(samples, coeff))
                        + 32768
                    )
                    >> 16
                    for channel in range(2)
                ]
                if not enabled & (1 << t):
                    x = y = 0
                angle = (phases[t] >> 22) * 2 * math.pi / 1024
                co = (round(32767 * math.cos(angle)) * gains[t]) >> 15
                si = (round(32767 * math.sin(angle)) * gains[t]) >> 15
                sums[0] += (x * co - y * si) >> 15
                sums[1] += (x * si + y * co) >> 15
                if advanced:
                    phases[t] = (phases[t] + incs[t]) & 0xFFFFFFFF
                    if enabled & moving_mask & (1 << t):
                        positions[t] += motion_steps[t]
                        if positions[t] < 0:
                            positions[t] = -positions[t]
                            motion_steps[t] = -motion_steps[t]
                            incs[t] = (-incs[t]) & 0xFFFFFFFF
                        elif positions[t] > motion_upper:
                            positions[t] = 2 * motion_upper - positions[t]
                            motion_steps[t] = -motion_steps[t]
                            incs[t] = (-incs[t]) & 0xFFFFFFFF
            if c >= ready_at:
                pending[c + 18] = sums
            history.append((ii, qq))
        flush = False
        if configure:
            requested = (mask, params[:4], params[4:8], params[8:12])
            next_motion = (params[12], params[13:17], params[17])
            if mask:
                commit_at = c + 4099
                next_active = requested
                next_restart = restart
            else:
                commit_at = None
                active = requested
                ready_at = 10**9
                flush = True
                if restart:
                    phases = [0] * 4
        elif commit_at == c:
            active = next_active
            ready_at = c + 4
            commit_at = None
            flush = True
            if next_restart:
                phases = [0] * 4
        if flush:
            motion_resume_at = c + 4
            moving_mask, motion_steps, upper = next_motion
            motion_steps = motion_steps.copy()
            motion_upper = upper << 48
            positions = [(d << 48) + (t << 46) for t, d in enumerate(active[1])]
            for t in range(4):
                if moving_mask & (1 << t):
                    positions[t] = min(positions[t], motion_upper)
            if advanced and not (restart if configure else next_restart):
                phases = [(p - i) & 0xFFFFFFFF for p, i in zip(phases, incs)]
            pending = {}
            held = (0, 0)
            clipped = 0
            clip_pending = 0
            ov = 0
    expected = [ov, *held, clipped]
    assert out == expected, f"cycle {c}: actual {out}, expected {expected}"
    checks += ov
print(
    f"PASS: {len(rows)} clocks, {checks} IQ outputs; old scene remains active during table reload; immediate mute; atomic handoff"
)
