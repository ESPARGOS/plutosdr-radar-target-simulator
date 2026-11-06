import random, subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
build = root / "build/tests"
build.mkdir(parents=True, exist_ok=True)
rng = random.Random(5)
rows = []
for cycle in range(100000):
    reset = cycle < 3
    cfg = cycle in (3, 10000, 15000, 20000, 25000, 30000, 35000, 40000, 45000, 50000)
    moving = int(cycle < 15000 or cycle >= 20000)
    enabled = int(cycle < 25000 or cycle >= 30000)
    # Accelerated stress trajectories cross integer and reflection boundaries.
    # Also check the tiny increment corresponding to a practical target velocity.
    step = round((0.013 if cycle < 35000 else -17 / 2385e6) * 2**48)
    inc = 1234567 if cycle < 35000 else 456
    edit_position = int(cycle < 10000 or cycle >= 45000)
    edit_velocity = int(cycle < 10000 or cycle >= 35000)
    initial, fraction, upper = 2, 60000, 9 if cycle < 40000 else 3
    if cycle >= 60000:
        block = (cycle - 60000) // 1000
        cfg = cycle % 1000 == 0
        upper = [1, 2, 12276][block % 3]
        initial = [0, upper, upper - 1, 16382][block % 4]
        fraction = [0, 65535, 32768][block % 3]
        step = [round(0.499999 * 2**48), -round(0.499999 * 2**48), 1, -1, 0][block % 5]
        moving = int(block % 7 != 0)
        enabled = int(block % 9 != 0)
        edit_position = int(block % 3 != 0)
        edit_velocity = int(block % 4 != 0)
    rows.append(
        [
            int(reset),
            int(cfg),
            int(rng.random() < 0.8),
            moving,
            enabled,
            edit_position,
            edit_velocity,
            int(cycle == 3),
            initial,
            fraction,
            upper,
            step,
            inc,
        ]
    )
(build / "motion-stimulus.txt").write_text(
    "".join(" ".join(map(str, r)) + "\n" for r in rows)
)
subprocess.run(
    [
        "iverilog",
        "-g2012",
        "-s",
        "tb",
        "-o",
        "motion-test",
        str(root / "rtl/target_motion.sv"),
        str(root / "tests/tb_motion.sv"),
    ],
    cwd=build,
    check=True,
)
subprocess.run(["vvp", "motion-test"], cwd=build, check=True)
pos = step = phase = inc = upper = active = moving = 0
configuration_wait = 0
for cycle, (row, line) in enumerate(
    zip(rows, (build / "motion-output.txt").read_text().splitlines())
):
    r, c, v, m, e, ep, ev, rp, d, f, u, s, p = row
    if r:
        pos = step = phase = inc = upper = active = moving = 0
        configuration_wait = 0
    elif c:
        new_upper = u << 48
        new_pos = (d << 48) + (f << 32) if ep or not moving else pos
        if m:
            new_pos = min(new_pos, new_upper)
        configuration = (new_pos, s if ev or not moving else step,
                         p if ev or not moving else inc,
                         0 if rp else phase, new_upper, e, m)
        configuration_wait = 3
    elif configuration_wait:
        if configuration_wait == 2:
            pos, step, inc, phase, upper, active, moving = configuration
        configuration_wait -= 1
    elif v:
        phase = (phase + inc) & 0xFFFFFFFF
        if active and moving:
            pos += step
            if pos < 0:
                pos = -pos
                step = -step
                inc = (-inc) & 0xFFFFFFFF
            elif pos > upper:
                pos = 2 * upper - pos
                step = -step
                inc = (-inc) & 0xFFFFFFFF
    expected = [pos >> 48, (pos >> 38) & 1023, (pos >> 32) & 65535, phase, inc]
    actual = list(map(int, line.split()))
    assert actual == expected, (cycle, row, actual, expected)
print(
    "PASS: 100000 motion clocks, fractional crossings, reflection, pause, selective edits and phase continuity"
)
