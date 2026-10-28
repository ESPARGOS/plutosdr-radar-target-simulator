# Tests and measurements

## Without hardware

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-test.txt
make test-local       # host Icarus Verilog + pinned ADI source
make test-analysis    # synthetic analysis/quality estimators
make test-web         # isolated preview server and Chromium
```

Or use `make test` for the HDL/control suite in the build container. The current
oracle exercises 15,000 clocks with random IQ, four independent paths, signed
Doppler, memory wrap, saturation, sample gaps, configuration, mute and restart.
AXI tests cover split write channels, strobes, backpressure and atomic CDC.
The patched ADI interface has its own regression. Candidate-specific experiment
tests are run explicitly, not as qualification of the current design.

`make test-web` starts and stops its own local preview and headless Chromium,
uses temporary profiles under `RTS_SCRATCH_DIR` (default `build/scratch`), and
writes logs/screenshots under `build/`. Set `CHROMIUM_BIN` if Chromium is not on
PATH. This isolated test browser disables its sandbox; it visits only the local
preview. The runner never contacts Pluto or ESPARGOS. Python syntax and shell
syntax checks also run in `.github/workflows/tests.yml`.

The latest local source-preparation results are recorded in
[validation/source-check.md](validation/source-check.md). The GitHub workflow
uses the official [checkout](https://github.com/actions/checkout) and
[setup-python](https://github.com/actions/setup-python) actions.

## On-device browser regression

Install `requirements-hardware.txt` and system libiio. Start an isolated Chromium
instance with CDP on port 9223 and origin `http://localhost:9223`, then run:

```sh
PLUTO_URL=http://192.168.4.1 RADAR_BROWSER_DEBUG_PORT=9223 \
  python3 tests/device_web_check.py
```

This test **changes hardware state**: scenes, gains and carrier. Export the current
scene and record your radio settings first. It leaves targets muted, restores the
gains it initially read, but does not restore the original scene/carrier. It
checks native API validation, gain readback, scene updates during dragging,
On/Off controls, zoom-panel selection, reserved legend space, scene import/export,
no click-to-add, bandwidth/sample-rate display and desktop/mobile layouts.
Screenshots are in `build/device-web-{desktop,mobile}.png`.

## RF measurements with ESPARGOS

Install a compatible [pyespargos](https://github.com/ESPARGOS/pyespargos) checkout
and its dependencies. Set `PYESPARGOS_PATH` or pass `--pyespargos`; the default
looks for `../ESPARGOS/pyespargos` beside this project. Set `ESPARGOS_HOST` or pass
`--host` for your receiver. `config/lab.example.json` is an illustrative settings
record, not an automatically loaded configuration file.

```sh
export PYESPARGOS_PATH=/path/to/pyespargos
python3 scripts/measure_espargos.py --host 192.168.1.100 \
  --scene config/four-targets.json --pluto-rx-gain 35 \
  --pluto-tx-attenuation 25 --seconds 6 --output build/four-targets.npz
python3 scripts/analyze_measurement.py build/four-targets.npz
```

The recorder configures one ESPARGOS transmitter and seven receivers, calibrates,
records muted baseline and active scene, and mutes both devices on exit. It
retains IQ, timestamps, waveform reference and configuration for analysis.
Run `--help` for two-tone, broadband, native-TX and ADC diagnostic options.
These advanced diagnostics require the specified compatible device/driver layout.

`scripts/mimo_radar_pluto.py --host ADDRESS --pyespargos PATH` launches the existing
MIMO demo with a compatible 20 MSa/s waveform and expanded range. It reads the
Pluto carrier but does not modify the pyespargos sources. A wider displayed range
cannot remove the waveform's physical range ambiguity.
