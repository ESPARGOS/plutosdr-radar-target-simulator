"""Plot independently measured zero-delay RF latency for each FPGA/clock profile."""

import json
from pathlib import Path
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

root = Path("build/latency")
old = ["before", "old-fpga-40m-no-fir", "old-fpga-60m-no-fir"]
new = ["new-fpga-20m", "new-fpga-40m", "new-fpga-60m"]


def latency(name):
    return json.loads((root / (name + ".json")).read_text())["targets"][0][
        "measured_delay_us"
    ]


old_values = list(map(latency, old))
new_values = list(map(latency, new))
fig, ax = plt.subplots(figsize=(8, 4))
x = list(range(3))
a = ax.bar(
    [i - 0.18 for i in x],
    old_values,
    width=0.36,
    label="Original FPGA",
    color="#637686",
)
b = ax.bar(
    [i + 0.18 for i in x], new_values, width=0.36, label="New FPGA", color="#37a95a"
)
ax.bar_label(a, fmt="%.3f µs")
ax.bar_label(b, fmt="%.3f µs")
ax.set(
    xticks=x,
    xticklabels=["20 MSa/s", "40 MSa/s", "60 MSa/s"],
    ylabel="Measured RF latency (µs)",
    ylim=(0, 4.1),
    title="Zero programmed delay · FIR-bypassed hardware profiles",
)
ax.legend()
fig.tight_layout()
fig.savefig(root / "comparison.png", dpi=170)
summary = {
    "baseline_us": old_values[0],
    "final_us": new_values[-1],
    "reduction_percent": 100 * (1 - new_values[-1] / old_values[0]),
    "old_fpga_us": old_values,
    "new_fpga_us": new_values,
    "rates_hz": [20e6, 40e6, 60e6],
    "fpga_cycles_removed": 16,
    "software_latency_subtraction": False,
}
(root / "comparison.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
