#!/usr/bin/env python3
"""Plot measured frequency-dependent Doppler and its error distribution."""
import argparse
import json
import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'build/matplotlib'))


def plot(result, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 8,
                         'axes.labelsize': 8, 'xtick.labelsize': 7, 'ytick.labelsize': 7,
                         'legend.fontsize': 7, 'pdf.fonttype': 42, 'axes.linewidth': .6})
    fig, axes = plt.subplots(2, 1, figsize=(3.45, 2.47), sharex=True,
                             gridspec_kw={'height_ratios': [.85, .8]}, layout='constrained')
    for mode, color, label in [('moving', '#258c4c', 'Continuous motion'),
                                ('fixed', '#2787b2', 'Fixed-delay Doppler')]:
        d = result['modes'][mode]
        f = np.asarray(d['frequencies_hz']) / 1e6
        expected = np.asarray(d['expected_hz'])
        median = np.asarray(d['median_hz'])
        low, high = np.asarray(d['p10_hz']), np.asarray(d['p90_hz'])
        # Leave a gap at the unused DC subcarrier.
        for mask in [f < 0, f > 0]:
            axes[0].fill_between(f[mask], low[mask], high[mask], color=color, alpha=.2)
            axes[0].plot(f[mask], median[mask], color=color, lw=1,
                         label=label if mask[0] else None)
            axes[1].fill_between(f[mask], 1000*(low[mask]-expected[mask]),
                                 1000*(high[mask]-expected[mask]), color=color, alpha=.2)
            axes[1].plot(f[mask], 1000*(median[mask]-expected[mask]), color=color, lw=.8)
        axes[0].plot(f, expected, '--', color=('#123e23' if mode == 'moving' else '#123c51'), lw=.8,
                     label=None)
    axes[0].set_ylabel('Doppler (Hz)')
    axes[0].set_yticks([39.6, 40.0, 40.4])
    axes[0].ticklabel_format(axis='y', style='plain', useOffset=False)
    axes[0].set_title('(a) Doppler across the signal band', loc='left', fontsize=8)
    for color, title, location in [('#258c4c', 'Continuous motion', 'upper left'),
                                    ('#2787b2', 'Fixed-delay Doppler', 'lower right')]:
        handles = [Line2D([], [], color=('#123e23' if title == 'Continuous motion' else '#123c51'),
                           ls='--', lw=.8, label='Theory'),
                   Line2D([], [], color=color, lw=1, label='Measurement')]
        legend = axes[0].legend(handles=handles, title=title, frameon=False,
                                loc=location, ncol=2, handlelength=1.5,
                                fontsize=6.5, title_fontsize=6.5, labelspacing=.15,
                                columnspacing=.7, handletextpad=.4, borderaxespad=.3)
        if location == 'upper left':
            axes[0].add_artist(legend)
    axes[1].axhline(0, color='0.3', ls='--', lw=.8)
    axes[1].set_ylabel('Error relative to\ntheory (mHz)')
    axes[1].set_title('(b) Difference from theory', loc='left', fontsize=8)
    axes[1].set_xlabel('Baseband frequency offset (MHz)')
    for ax in axes:
        ax.spines[['top', 'right']].set_visible(False)
        ax.grid(color='0.9', lw=.5)
        ax.set_xlim(-28, 28)
        ax.set_xticks([-20, -10, 0, 10, 20])
    fig.savefig(output)
    preview = (ROOT / 'build' / output.with_suffix('.png').name
               if output.parent == ROOT / 'figures' else output.with_suffix('.png'))
    preview.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(preview, dpi=180)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary', type=Path, nargs='?', default=ROOT / 'data/ofdm-doppler.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'figures/ofdm-doppler.pdf')
    args = parser.parse_args()
    plot(json.loads(args.summary.read_text()), args.output)


if __name__ == '__main__':
    main()
