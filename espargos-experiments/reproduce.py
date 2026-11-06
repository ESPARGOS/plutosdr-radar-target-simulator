#!/usr/bin/env python3
"""Acquire and analyze the paper experiments. Acquisition is a dry run unless --execute is set."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
RECIPES = json.loads((ROOT / 'config/paper-recipes.json').read_text())
GROUPS = {
    'range': ['packed-array-reference', 'v28-range'],
    'trajectory': ['trajectory-gap-free-reference', 'trajectory-gap-free'],
    'feedback': ['v28-feedback-gain', 'v28-feedback-low-source'],
    'delay': [n for n in RECIPES if n.startswith('review-clean-sweep')],
    'motion': [n for n in RECIPES if n.startswith('review-') and 'sweep' not in n],
    'latency': ['v28-final-zero20', 'v28-final-zero56'],
    'standard': ['v28-zero-standard20', 'v28-zero-standard30', 'v28-sweep-standard30'],
}


def run(command, execute=True):
    print(shlex.join(map(str, command)), flush=True)
    if execute:
        subprocess.run(command, cwd=ROOT, check=True)


def capture(names, args):
    for name in names:
        recipe = RECIPES[name]
        scene = args.output / (name + '-scene.json')
        if args.execute:
            scene.write_text(json.dumps(recipe['scene'], indent=2) + '\n')
        command = [sys.executable, 'scripts/measure_espargos.py',
                   '--host', args.host, '--pluto', args.pluto,
                   '--pyespargos', str(Path(args.pyespargos).resolve()),
                   '--scene', str(scene), '--output', str(args.output / (name + '.npz'))]
        for key, value in recipe['options'].items():
            option = '--' + key.replace('_', '-')
            if isinstance(value, bool):
                if value:
                    command.append(option)
            else:
                command.append(option)
                command.extend(map(str, value if isinstance(value, list) else [value]))
        run(command, args.execute)


def analyze(names, output):
    for name in names:
        source = str(output / (name + '.npz'))
        if name == 'v28-range':
            run([sys.executable, 'scripts/analyze_measurement.py', source,
                 '--array-reference', str(output / 'packed-array-reference.npz'),
                 '--doppler-limit', '18', '--doppler-step', '.02'])
        elif name == 'trajectory-gap-free':
            run([sys.executable, 'scripts/analyze_trajectory.py', source,
                 '--array-reference', str(output / 'trajectory-gap-free-reference.npz'),
                 '--array-phase-model', 'constant', '--window', '2', '--step', '1',
                 '--range-window', '60', '500'])
        elif 'zero' in name:
            run([sys.executable, 'scripts/analyze_measurement.py', source])
        elif name.startswith('v28-feedback'):
            run([sys.executable, 'scripts/analyze_feedback.py', source])
        elif 'sweep' in name:
            run([sys.executable, 'scripts/analyze_delay_sweep.py', source])
        elif name.startswith('review-'):
            run([sys.executable, 'scripts/analyze_motion.py', source, '--bandwidth', '5'])


def figures(output):
    run([sys.executable, 'figures/prepare_data.py', str(output),
         '--range', 'v28-range', '--range-latency-us', '.4140625',
         '--trajectory', 'trajectory-gap-free', '--trajectory-latency-us', '.4140625'])
    records = []
    for name, label in [('v28-feedback-gain', 'Original source power'),
                        ('v28-feedback-low-source', 'Source power reduced by 6 dB')]:
        record = json.loads((output / (name + '-feedback.json')).read_text())
        # Only numerical results go into the reduced figure data.
        records.append(dict(label=label, rows=record['rows']))
    (ROOT / 'data/feedback-gain.json').write_text(json.dumps(records, indent=2) + '\n')
    import numpy as np
    sys.path.insert(0, str(ROOT.parent / 'scripts'))
    from generate_fractional_rom import table
    coefficients = table(True) / 65536
    np.savetxt(ROOT / 'data/fractional-coefficients.csv',
               np.column_stack((np.arange(1024) / 1024, coefficients)),
               delimiter=',', header='mu,h0,h1,h2,h3,h4,h5', comments='')
    for script in ['plot_results.py', 'plot_trajectory.py', 'plot_feedback.py',
                   'plot_fractional_coefficients.py']:
        run([sys.executable, 'figures/' + script])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['capture', 'analyze', 'figures'])
    p.add_argument('group', nargs='?', choices=[*GROUPS, 'all'], default='all')
    p.add_argument('--output', type=Path, default=ROOT / 'build/measurements')
    p.add_argument('--host', default=os.environ.get('ESPARGOS_HOST'))
    p.add_argument('--pluto', default=os.environ.get('PLUTO_HOST', '192.168.2.1'))
    p.add_argument('--pyespargos', default=os.environ.get('PYESPARGOS_PATH'))
    p.add_argument('--execute', action='store_true', help='Enable live RF acquisition')
    args = p.parse_args()
    args.output = args.output.resolve()
    if args.action == 'capture' and (not args.host or not args.pyespargos):
        p.error('Capture requires --host and --pyespargos (or their environment variables)')
    (ROOT / 'build').mkdir(exist_ok=True)
    os.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'build/matplotlib'))
    if args.action != 'capture' or args.execute:
        args.output.mkdir(parents=True, exist_ok=True)
    names = [n for group, members in GROUPS.items() if group != 'standard' for n in members] if args.group == 'all' else GROUPS[args.group]
    if args.action == 'capture':
        capture(names, args)
    elif args.action == 'analyze':
        analyze(names, args.output)
    else:
        figures(args.output)


if __name__ == '__main__':
    main()
