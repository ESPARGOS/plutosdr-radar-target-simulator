#!/usr/bin/env python3
"""Plot requested and measured range changes from independent delay sweeps."""
import argparse
import json
import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "build/matplotlib"))


def plot(result, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 7,
                         "axes.labelsize": 7, "xtick.labelsize": 6.5,
                         "ytick.labelsize": 6.5, "legend.fontsize": 6,
                         "pdf.fonttype": 42, "axes.linewidth": .6})
    if not result["modes"]:
        raise ValueError("No sweep results to plot")
    maximum = max(max(d["requested_mm"]) for d in result["modes"].values())
    lower = min(0, min(min(d["p10_mm"]) for d in result["modes"].values()))
    upper = max(maximum, max(max(d["p90_mm"]) for d in result["modes"].values()))
    fig, axes = plt.subplots(1, 2, figsize=(3.45, 2.25), sharex=True, sharey=True, layout="constrained")
    for ax, mode, label in zip(axes, ["overclocked", "standard"],
                               ["(a) Overclocked", "(b) Standard"]):
        ax.plot([0, maximum], [0, maximum], "--", color="0.35", lw=.9, label="Ideal")
        if mode in result["modes"]:
            data = result["modes"][mode]
            x = np.array(data["requested_mm"])
            ax.fill_between(x, data["p10_mm"], data["p90_mm"], color="#2787b2",
                            alpha=.23, label="10th–90th percentiles")
            ax.plot(x, data["median_mm"], "o-", color="#2787b2", ms=2.5, lw=.8,
                    label="Measured median")
        ax.set_title(label, loc="left", fontsize=7.5)
        ax.set_xlabel("Requested range\nchange (mm)")
        ax.set_aspect("equal", adjustable="box")
        from matplotlib.ticker import MaxNLocator
        ax.xaxis.set_major_locator(MaxNLocator(nbins=3, steps=[1, 2, 5, 10]))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=3, steps=[1, 2, 5, 10]))
        ax.set_xlim(0, maximum * 1.05)
        ax.set_ylim(lower - maximum * .025, upper + maximum * .075)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(color="0.9", lw=.5)
    axes[0].set_ylabel("Measured range change (mm)")
    axes[0].legend(frameon=False, loc="upper left", handlelength=1.3,
                   borderaxespad=.3)
    fig.savefig(output)
    preview = (ROOT / "build" / output.with_suffix(".png").name
               if output.parent == ROOT / "figures" else output.with_suffix(".png"))
    preview.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(preview, dpi=180)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path, nargs="?", default=ROOT / "data/range-steps.json")
    parser.add_argument("--output", type=Path, default=ROOT / "figures/range-steps.pdf")
    args = parser.parse_args()
    plot(json.loads(args.summary.read_text()), args.output)


if __name__ == "__main__":
    main()
