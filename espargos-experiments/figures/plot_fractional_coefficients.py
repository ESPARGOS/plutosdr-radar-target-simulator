#!/usr/bin/env python3
"""Compare the table-defined interpolation kernel with ideal sinc interpolation."""
from pathlib import Path
import numpy as np
from matplotlib.lines import Line2D
from plot_results import plt, GREEN

ROOT = Path(__file__).resolve().parent.parent

def main():
    data = np.loadtxt(ROOT / 'data/fractional-coefficients.csv', delimiter=',', skiprows=1)
    row = data[np.flatnonzero(np.isclose(data[:, 0], .5))[0]]
    taps = np.arange(6)
    position = np.linspace(-.65, 5.65, 600)
    ideal = np.sinc(taps - 2.5)
    # h_l(mu) = g(l - 2 - mu). Each tap supplies one adjacent interval
    # of the kernel. Join the quantized table points for visualization only.
    coordinates = (taps[None, :] - 2 - data[:, 0, None]).ravel()
    values = data[:, 1:].ravel()
    order = np.argsort(coordinates)
    coordinates = np.r_[-3., coordinates[order]]
    values = np.r_[0., values[order]]
    assert np.all(np.diff(coordinates) > 0)
    assert np.allclose(np.interp(taps - 2.5, coordinates, values), row[1:])
    kernel = np.interp(position - 2.5, coordinates, values, left=0., right=0.)
    fig, ax = plt.subplots(figsize=(3.5, 1.85))
    fig.subplots_adjust(left=.15, right=.97, bottom=.25, top=.78)
    ax.axhline(0, color='.6', linewidth=.5)
    ax.plot(position, np.sinc(position - 2.5), '--', color='.5', linewidth=.85)
    ax.vlines(taps, 0, ideal, color='.6', linewidth=.75)
    ax.plot(taps, ideal, 'o', color='.5', markerfacecolor='white', markersize=4, markeredgewidth=.8)
    ax.plot(position, kernel, color=GREEN, linewidth=1.35)
    ax.vlines(taps, 0, row[1:], color=GREEN, linewidth=1.1)
    ax.plot(taps, row[1:], 'o', color=GREEN, markersize=3.8)
    ax.set(xlim=(-.65,5.65), ylim=(-.3,1.05), xlabel='Sample position (samples)', ylabel='Kernel value')
    ax.set_xticks(taps)
    ax.set_yticks([0,.5,1])
    ax.grid(axis='y', alpha=.15)
    ax.legend(handles=[Line2D([],[],color='.5',linestyle='--',marker='o',markerfacecolor='white',
                             markersize=4,linewidth=.85,label='Ideal sinc'),
                       Line2D([],[],color=GREEN,marker='o',markersize=4,linewidth=1.3,
                             label='Implemented kernel')],
              ncol=2,loc='lower center',bbox_to_anchor=(.5,1.02),frameon=False,
              handlelength=1.4,handletextpad=.4,columnspacing=.8)
    fig.text(.02,.92,'(b)')
    fig.savefig(ROOT / 'figures/fractional-coefficients.pdf')
    fig.savefig(ROOT / 'build/fractional-coefficients.png', dpi=180)
    plt.close(fig)

if __name__ == '__main__':
    main()
