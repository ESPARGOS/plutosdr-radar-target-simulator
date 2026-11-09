#!/usr/bin/env python3
"""Compare the table-defined interpolation filter with ideal sinc interpolation."""
from pathlib import Path
import numpy as np
from matplotlib.lines import Line2D
from plot_results import plt, GREEN

ROOT = Path(__file__).resolve().parent.parent

def main():
    data = np.loadtxt(ROOT / 'data/fractional-coefficients.csv', delimiter=',', skiprows=1)
    row = data[np.argmin(np.abs(data[:, 0] - .6))]
    mu = row[0]
    delay = 2 + mu
    taps = np.arange(6)
    position = np.linspace(-.65, 5.75, 600)
    # h_l(mu) = g(l - 2 - mu). Each tap supplies one adjacent interval
    # of the interpolation function. Join the quantized table points for visualization only.
    coordinates = (taps[None, :] - 2 - data[:, 0, None]).ravel()
    values = data[:, 1:].ravel()
    order = np.argsort(coordinates)
    coordinates = np.r_[-3., coordinates[order]]
    values = np.r_[0., values[order]]
    assert np.all(np.diff(coordinates) > 0)
    assert np.allclose(np.interp(taps - delay, coordinates, values), row[1:])
    # Draw every lookup-table entry rather than resampling the reconstructed
    # function onto the coarser grid used for the ideal sinc reference.
    filter_positions = np.r_[-.65, coordinates + delay, 5 + mu, 5.75]
    filter_values = np.r_[0., values, 0., 0.]
    plt.rcParams['path.simplify'] = False
    fig, ax = plt.subplots(figsize=(3.5, 2.05))
    fig.subplots_adjust(left=.15, right=.97, bottom=.23, top=.65)
    ax.axhline(0, color='.6', linewidth=.5)
    ax.plot(position, np.sinc(position - delay), '--', color='.5', linewidth=.85)
    ax.plot(filter_positions, filter_values, color=GREEN, linewidth=1.35)
    ax.vlines(taps, 0, row[1:], color=GREEN, linewidth=1.1)
    ax.plot(taps, row[1:], 'o', color=GREEN, markersize=3.8)
    # Show the fractional offset at the left, independently of the fixed
    # two-sample delay that centers the filter.
    ax.vlines(0, 0, 1.2, color='.55', linewidth=.6, linestyles=':')
    ax.vlines(mu, 0, 1.2, color='.55', linewidth=.6, linestyles=':')
    ax.annotate('', xy=(mu, .85), xytext=(0, .85),
                arrowprops=dict(arrowstyle='<->', color='.25', lw=.7,
                                shrinkA=0, shrinkB=0, mutation_scale=7))
    ax.text(mu / 2, .95, r'$\mu \approx 0.6$',
            ha='center', va='bottom', fontsize=7)
    ax.set(xlim=(-.65,5.75), ylim=(-.3,1.2),
           xlabel=r'FIR tap index $\ell$', ylabel='Coefficient value')
    shifted = ax.secondary_xaxis('top', functions=(lambda x: x - mu, lambda u: u + mu))
    shifted.set_xlabel(r'Shifted coordinate $\ell-\mu$', fontsize=7, labelpad=5)
    shifted.set_xticks(taps)
    shifted.tick_params(labelsize=7)
    ax.set_xticks(taps)
    ax.set_yticks([0,.5,1])
    ax.grid(axis='y', alpha=.15)
    fig.legend(handles=[Line2D([],[],color='.5',linestyle='--',linewidth=.85,label='Ideal sinc'),
                       Line2D([],[],color=GREEN,marker='o',markersize=4,linewidth=1.3,
                             label=r'Least-squares design $g(\ell-2-\mu)$')],
              ncol=2,loc='upper center',bbox_to_anchor=(.56,1.0),frameon=False,
              handlelength=1.4,handletextpad=.4,columnspacing=.8,fontsize=7)
    fig.text(.02,.94,'(b)')
    fig.savefig(ROOT / 'figures/fractional-coefficients.pdf')
    fig.savefig(ROOT / 'build/fractional-coefficients.png', dpi=180)
    plt.close(fig)

if __name__ == '__main__':
    main()
