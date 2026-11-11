#!/usr/bin/env python3
"""Measured moving-target range and velocity, with independent command traces."""
from pathlib import Path
import numpy as np
from plot_results import plt

ROOT = Path(__file__).resolve().parent.parent

def main():
    second_pass_style = (0, (1, 5))
    with np.load(ROOT / "data/trajectory.npz") as data:
        time = data["time_s"]
        distance = data["range_m"]
        velocity = data["velocity_m_s"]
        window = data["velocity_range_window_m"]
        included = (distance >= window[0]) & (distance <= window[1])
        reference = data["range_power"][:, included].max()
        fig, axes = plt.subplots(2, 1, figsize=(3.5, 3.22), sharex=True)
        fig.subplots_adjust(left=.17, right=.78, bottom=.13, top=.906, hspace=.15)
        for index, (axis, coordinate, key, label) in enumerate(zip(
            axes, [distance, velocity], ["range_power", "velocity_power"],
            ["Equivalent range (m)", "Radial velocity (m/s)"]
        )):
            power = 10 * np.log10(np.maximum(data[key].T / reference, 1e-12))
            image = axis.pcolormesh(time, coordinate, power, cmap="magma",
                                   vmin=-35, vmax=0, shading="auto", rasterized=True)
            axis.set_ylabel(label)
            axis.text(.03, .94 if index == 0 else .84, f"({chr(97 + index)})", color="white",
                      transform=axis.transAxes, va="top")
        for target in range(data["command_range_m"].shape[1]):
            for axis, key in zip(axes, ["command_range_m", "command_velocity_m_s"]):
                axis.plot(data["command_time_s"], data[key][:, target],
                          color="cyan", linestyle="-", linewidth=.55)
        # A second pass adds the two selected path delays and Dopplers.
        period = 299792458 / (2 * float(data["carrier_hz"]) * float(data["snapshot_spacing_seconds"]))
        for first, second in [(0, 0), (0, 1), (1, 1)]:
            ranges = data["command_range_m"][:, first] + data["command_range_m"][:, second]
            speeds = data["command_velocity_m_s"][:, first] + data["command_velocity_m_s"][:, second]
            speeds = (speeds + period / 2) % period - period / 2
            visible = (ranges >= window[0]) & (ranges <= window[1])
            # Break lines at velocity reversals and alias boundaries.
            speed_plot = np.where(visible, speeds, np.nan)
            speed_plot[1:][abs(np.diff(speeds)) > 1] = np.nan
            axes[0].plot(data["command_time_s"], ranges, linestyle=second_pass_style, color="#a6ef8a", linewidth=.7, dash_capstyle="round")
            axes[1].plot(data["command_time_s"], speed_plot, linestyle=second_pass_style, color="#a6ef8a", linewidth=.7, dash_capstyle="round")
        from matplotlib.lines import Line2D
        fig.legend(handles=[Line2D([], [], color="#168caa", linestyle="-", linewidth=.8, label="Target settings"),
                            Line2D([], [], color="#438b35", linestyle=second_pass_style, linewidth=.7, dash_capstyle="round", label="Self-interference (second pass)")],
                   loc="upper center", bbox_to_anchor=(.48, 1.02), ncol=2, frameon=False)
        axes[0].set_ylim(50, 515)
        axes[0].set_yticks([100, 200, 300, 400, 500])
        axes[1].set(xlim=(0, 250), ylim=(-2.65, 2.65), xlabel="Time (s)")
        axes[1].set_yticks([-2, -1, 0, 1, 2])
        axes[1].set_xticks([0, 60, 120, 180, 240])
        colorbar = fig.colorbar(image, cax=fig.add_axes([.81, .13, .025, .776]))
        colorbar.set_label("Relative power (dB)", fontsize=7)
        colorbar.set_ticks([-30, -20, -10, 0])
        fig.savefig(ROOT / "figures/trajectory.pdf", dpi=300)
        fig.savefig(ROOT / "build/trajectory.png", dpi=180)
        plt.close(fig)

if __name__ == "__main__":
    main()
