# Testing

## Without hardware

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-test.txt
make test-local       # host Icarus Verilog + pinned ADI source
make test-analysis    # synthetic analysis/quality estimators
make test-web         # isolated preview server and Chromium
```

Or use `make test` for the HDL/control suite in the build container. The bit-exact
reference model checks 15,000 clocks with random IQ, four independent paths, signed
Doppler, memory wrap, saturation, sample gaps, configuration, mute and restart.
AXI tests cover split write channels, strobes, backpressure and atomic CDC.
There is also a test for the patched ADI interface. Tests for older experimental
designs are kept separately and can be run individually.

`make test-web` starts and stops its own local preview and headless Chromium,
uses temporary profiles under `RTS_SCRATCH_DIR` (default `build/scratch`), and
writes logs/screenshots under `build/`. Set `CHROMIUM_BIN` if Chromium is not on
PATH. The test browser runs with its sandbox disabled and visits only the local
preview. It does not connect to Pluto or ESPARGOS. Python syntax and shell
syntax checks also run in `.github/workflows/tests.yml`.

Results from the clean-checkout test are recorded in
[validation/source-check.md](validation/source-check.md). The GitHub workflow
uses the official [checkout](https://github.com/actions/checkout) and
[setup-python](https://github.com/actions/setup-python) actions.

## Testing the Pluto web interface

Install `requirements-hardware.txt` and system libiio. Start an isolated Chromium
instance with CDP on port 9223 and origin `http://localhost:9223`, then run:

```sh
PLUTO_URL=http://192.168.4.1 RADAR_BROWSER_DEBUG_PORT=9223 \
  python3 tests/device_web_check.py
```

This test changes the targets, radio gains and carrier frequency. Export the current
scene and record your radio settings first. It leaves targets muted, restores the
gains it initially read, but does not restore the original scene/carrier. It
checks the API and hardware readback, dragging, On/Off controls, zoom selection,
scene import/export and desktop/mobile layouts. It also checks that the legend
keeps its space and that clicking empty plot space leaves the scene alone.
Screenshots are in `build/device-web-{desktop,mobile}.png`.

## RF measurements with ESPARGOS

Install a compatible [pyespargos](https://github.com/ESPARGOS/pyespargos) checkout
and its dependencies. Set `PYESPARGOS_PATH` or pass `--pyespargos`; the default
looks for `../ESPARGOS/pyespargos` beside this project. Set `ESPARGOS_HOST` or pass
`--host` for your receiver. `config/lab.example.json` shows an example setup; the scripts do not load it
automatically.

```sh
export PYESPARGOS_PATH=/path/to/pyespargos
python3 scripts/measure_espargos.py --host 192.168.1.100 \
  --scene config/four-targets.json --pluto-rx-gain 35 \
  --pluto-tx-attenuation 25 --seconds 6 --output build/four-targets.npz
python3 scripts/analyze_measurement.py build/four-targets.npz
```

The recorder sets up one ESPARGOS transmitter and seven receivers, runs
calibration, then records a baseline with the targets muted and a capture with
them enabled. It saves the IQ samples, timestamps, reference waveform and settings,
and mutes both devices when it exits.
Run `--help` for two-tone, broadband, native-TX and ADC diagnostic options.
Check the device and driver requirements before using the ADC diagnostics.

`scripts/mimo_radar_pluto.py --host ADDRESS --pyespargos PATH` launches the existing
MIMO demo with a compatible 20 MSa/s waveform and expanded range. It reads the
Pluto carrier but does not modify the pyespargos sources. A wider displayed range
cannot remove the waveform's physical range ambiguity.
