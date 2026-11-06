#!/usr/bin/env python3
"""Gain dependence of the first repeated echo in the antenna feedback loop."""
import json
from pathlib import Path
import numpy as np
from plot_results import plt, BLUE, GREEN

ROOT = Path(__file__).resolve().parent.parent

def main():
    records = json.loads((ROOT / 'data/feedback-gain.json').read_text())
    fig, ax = plt.subplots(figsize=(3.5, 2.25))
    fig.subplots_adjust(left=.18, right=.97, bottom=.22, top=.97)
    for index, (record, color, marker) in enumerate(zip(records, [BLUE, GREEN], ['o', 's'])):
        rows = [r for r in record['rows'] if r['ratio_db'] is not None and min(r['snr_db']) >= 6]
        gains = sorted(set(r['tx_gain_db'] for r in rows))
        quartiles = np.array([np.quantile([r['ratio_db'] for r in rows if r['tx_gain_db'] == gain], [.25, .5, .75]) for gain in gains])
        middle = quartiles[:, 1]
        ax.errorbar(gains, middle, yerr=[middle-quartiles[:, 0], quartiles[:, 2]-middle],
                    fmt=marker, color=color, markersize=4, capsize=2, linewidth=.8,
                    markerfacecolor='white' if index else color, label=record['label'])
        if index == 0:
            # Only the offset is fitted. Linear feedback predicts unit slope.
            offset = np.mean([r['ratio_db'] - r['tx_gain_db'] for r in rows])
            x = np.array([-22, -11])
            ax.plot(x, x+offset, '--', color='.45', linewidth=.8, label='Linear feedback prediction', zorder=0)
    ax.set(xlabel='Pluto TX gain (dB)', ylabel='Echo power ratio (dB)',
           xlim=(-22, -11), ylim=(-31, -18))
    ax.set_xticks([-21, -18, -15, -12])
    ax.text(.03, .96, '(b)', transform=ax.transAxes, va='top')
    ax.grid(alpha=.2)
    ax.legend(loc='lower right', frameon=False, fontsize=6.5)
    fig.savefig(ROOT / 'figures/feedback.pdf')
    fig.savefig(ROOT / 'build/feedback.png', dpi=180)
    plt.close(fig)

if __name__ == '__main__':
    main()
