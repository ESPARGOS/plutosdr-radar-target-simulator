# ESPARGOS experiments

Optional acquisition, analysis and plotting tools for the radar target simulator
paper. The simulator itself does not depend on ESPARGOS or anything in this
folder. See [demo.md](demo.md) for the interactive MIMO radar example.

## Setup

Use a Pluto running the simulator firmware and an ESPARGOS array with IQ-capable
firmware. Place Pluto's RX and TX antennas in front of the array. The recordings
use one array transmitter and seven receivers. Keep antenna positions unchanged
between a reference recording and its measurement.

Install Python 3.10+, system libiio, `sshpass`, and a compatible
[pyespargos checkout](https://github.com/ESPARGOS/pyespargos). From this folder:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pip install -r /path/to/pyespargos/requirements.txt
export PYESPARGOS_PATH=/path/to/pyespargos
export ESPARGOS_HOST=YOUR_ARRAY_ADDRESS
export PLUTO_HOST=192.168.2.1
```

Select overclocked mode on Pluto and enable its tuning range extension before
acquisition. The paper recipes use a 2385 MHz carrier and up to 56 MHz simulator
bandwidth. Export your current scene first: acquisition changes radio settings
and targets, then mutes both devices. It does not restore their previous state.

## Reproduce the measurements

`reproduce.py` uses the waveform, radio and scene settings in
[config/paper-recipes.json](config/paper-recipes.json). It prints acquisition
commands without running them unless you add `--execute`:

```sh
python3 reproduce.py capture trajectory            # inspect commands
python3 reproduce.py capture trajectory --execute  # acquire reference and motion
python3 reproduce.py analyze trajectory
```

| Group | Measurement |
| --- | --- |
| `range` | Independent array reference and four echoes out to about 11.6 km |
| `trajectory` | Independent reference and 250 s of two moving targets, initially +2 and −1.5 m/s |
| `feedback` | TX gain sweeps at two radar source powers |
| `delay` | Five fractional-delay sweeps through one sample interval |
| `latency` | Minimum delay at 20 and 56 MHz bandwidth in overclocked mode |
| `standard` | Minimum delay at 20 and 30.72 MHz, plus a fractional-delay sweep |
| `motion` | Three interleaved repeats of fractional motion, whole-sample motion and fixed delay |

Use `all` to run all overclocked-mode groups. Run `standard` separately after
selecting standard mode in the web interface. The `motion` comparison
requires an extra helper on Pluto, described in [measurement notes](measurements.md).
The whole-sample mode is a comparison baseline, not the simulator's normal motion.

```sh
python3 reproduce.py capture all --execute
python3 reproduce.py analyze all
python3 reproduce.py figures
# After selecting standard mode in the web interface:
python3 reproduce.py capture standard --execute
python3 reproduce.py analyze standard
```

Raw recordings and analysis go into `build/measurements/`. Use `--output PATH`
on each command to select another directory. The last command extracts reduced
data into `data/` and renders the paper's measurement plots and interpolation
kernel into `figures/`. These generated files are ignored by Git.

RF powers, noise and antenna feedback depend on placement and equipment. These
recipes reproduce the procedure and processing, not identical numerical results.
The trajectory uses uniformly spaced pilots without an interior DC gap and
constant receiver phase weights from its independent reference. No target-position
mask is applied to the power maps. Optional native ADC diagnostics are omitted
from the recipes because they are not inputs to the paper plots.

## Offline checks

Run `make test` for synthetic capture and analysis tests. They require no hardware
and are independent of the simulator's normal test suite. Individual tools accept
`--help`. All code in this folder uses the project's [GPLv3 license](../LICENSE).
