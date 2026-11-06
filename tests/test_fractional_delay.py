from pathlib import Path
import random, subprocess, sys

root = Path(__file__).resolve().parents[1]
build = root / "build/tests"
build.mkdir(parents=True, exist_ok=True)
rng = random.Random(42)
rows = []
for cycle in range(80000):
    reset = int(cycle < 3 or 41000 <= cycle < 41003)
    valid = int(rng.random() < 0.8)
    d = (
        rng.choice([0, 1, 2, 3, 7, 8, 2047, 4095, 12276])
        if cycle < 40000 or cycle >= 60000
        else int((cycle - 40000) / 512) % 16
    )
    frac = rng.randrange(1024) if cycle < 40000 or cycle >= 60000 else cycle % 1024
    rows.append(
        (
            reset,
            valid,
            rng.randrange(-2048, 2048) * 16,
            rng.randrange(-2048, 2048) * 16,
            d,
            frac,
            int(cycle < 41000),
        )
    )
(build / "fractional-stimulus.txt").write_text(
    "".join(" ".join(map(str, r)) + "\n" for r in rows)
)
subprocess.run(
    [
        "iverilog",
        "-g2012",
        "-s",
        "tb",
        "-o",
        "fractional-test",
        str(root / "rtl/fractional_delay.sv"),
        str(root / "rtl/fractional_rom.sv"),
        str(root / "tests/tb_fractional.sv"),
    ],
    cwd=build,
    check=True,
)
subprocess.run(["vvp", "fractional-test"], cwd=build, check=True)
sys.path.insert(0, str(root / "scripts"))
from generate_fractional_rom import coefficients

coeff = [[coefficients(i, fast) for i in range(1024)] for fast in (False, True)]
history = []
pending = {}
held = [0, 0]
checks = 0
for cycle, (row, line) in enumerate(
    zip(rows, (build / "fractional-output.txt").read_text().splitlines())
):
    reset, valid, i, q, d, frac, fast = row
    if reset:
        history = []
        pending = {}
        held = [0, 0]
        expected = [0, 0, 0]
    else:
        ov = int(cycle in pending)
        if ov:
            held = pending.pop(cycle)
            checks += 1
        expected = [ov, *held]
        if valid:
            history.append([i, q])
            taps = [
                history[-1 - d - k] if len(history) > d + k else [0, 0]
                for k in range(8)
            ]
            pending[cycle + 12] = [
                (sum(x[channel] * c for x, c in zip(taps, coeff[fast][frac])) + 32768)
                >> 16
                for channel in range(2)
            ]
    fields = line.split()
    assert int(fields[0]) == expected[0], (cycle, row, fields, expected)
    if expected[0] or reset:
        actual = list(map(int, fields))
        assert actual == expected, (cycle, row, actual, expected)
print(
    f"PASS: {checks} fractional outputs, random delay/fraction, long-buffer wrap, startup, reset and sample gaps"
)
