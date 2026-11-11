#!/usr/bin/env python3
"""Measured four-target range–velocity map."""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "build/matplotlib"))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

C, FC = 299792458, 2385e6
GREEN, BLUE, GOLD = "#258c4c", "#2787b2", "#ba831d"
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 8,
        "axes.labelsize": 8,
        "legend.fontsize": 6.7,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "axes.linewidth": 0.6,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
    }
)


def range_doppler(ax):
    settings = json.loads((ROOT / "data/four-target-settings.json").read_text())
    with np.load(ROOT / "data/four-targets.npz") as data:
        velocity = -data["doppler_hz"] * C / (2 * FC)
        distance = data["delay_us"] * C / 2e9
        # Preserve narrow peaks when the analysis grid is finer than the printed
        # image. Every display cell contains the maximum of its original bins.
        power = data["power_db"] - settings.get("normalization_db", 0)
        vstep = int(np.ceil(len(velocity) / 128))
        rstep = int(np.ceil(len(distance) / 256))
        padding = ((0, -len(velocity) % vstep), (0, -len(distance) % rstep))
        padded = np.pad(power, padding, constant_values=-np.inf)
        reduced = padded.reshape(
            padded.shape[0] // vstep, vstep, padded.shape[1] // rstep, rstep
        ).max(axis=(1, 3))

        def edges(values, stride):
            step = values[1] - values[0]
            return np.r_[
                values[np.arange(0, len(values), stride)] - step / 2,
                values[-1] + step / 2,
            ]

        image = ax.pcolormesh(
            edges(velocity, vstep),
            edges(distance, rstep),
            reduced.T,
            shading="flat",
            cmap="magma",
            vmin=-35,
            vmax=0,
            rasterized=True,
        )
    for i, target in enumerate(settings["targets"], 1):
        v = -target["doppler_hz"] * C / (2 * FC)
        r = (target["delay_us"] + settings["hardware_delay_us"]) * C / 2e9
        ax.plot(v, r, marker="o", ms=10, mfc="none", mec="cyan", mew=0.8)
        label = f"{i} ({r:.1f} km)" if i == len(settings["targets"]) else str(i)
        ax.annotate(
            label,
            (v, r),
            xytext=(-10 if v > 0 else 8, -12 if i == 4 else 5),
            textcoords="offset points",
            ha="right" if v > 0 else "left",
            color="white",
            fontsize=8,
        )
    maximum = (
        max(t["delay_us"] + settings["hardware_delay_us"] for t in settings["targets"])
        * C
        / 2e9
    )
    ax.set(
        xlabel="Doppler-equivalent velocity (m/s)",
        ylabel="Equivalent range (km)",
        xlim=(float(velocity.min()), float(velocity.max())),
        ylim=(0, maximum * 1.06),
    )
    ax.text(
        0.97,
        0.97,
        "Requested targets",
        color="white",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=7,
    )
    colorbar = ax.figure.colorbar(
        image, ax=ax, orientation="vertical", pad=0.025, fraction=0.035, aspect=25
    )
    colorbar.set_label("Relative power (dB)", fontsize=7)
    colorbar.set_ticks([-30, -20, -10, 0])


def main():
    fig, ax = plt.subplots(figsize=(3.5, 2.83))
    fig.subplots_adjust(left=.16,right=.85,bottom=.166,top=.905)
    range_doppler(ax)
    fig.savefig(ROOT / 'figures/results.pdf', dpi=300)
    fig.savefig(ROOT / 'build/results.png', dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
