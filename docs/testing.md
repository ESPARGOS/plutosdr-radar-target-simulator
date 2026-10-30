# Testing

## Without hardware

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-test.txt
make test-local       # host Icarus Verilog + pinned ADI source
make test-analysis    # synthetic analysis/quality estimators
make test-native      # native controls and CGI failure cases (C compiler)
make test-ui-model    # scene conversion and request queue (Node.js 18+)
make test-provenance  # stale source/artifact rejection
make test-release     # release checksums and source archive contents
make test-web         # isolated preview server and Chromium
```

Or use `make test` for the HDL/control suite in the build container. The bit-exact
reference model checks 15,000 clocks with random IQ, four independent paths, signed
Doppler, memory wrap, saturation, sample gaps, configuration, mute and restart.
AXI tests cover split write channels, strobes, backpressure and atomic CDC.
There is also a test for the patched ADI interface.

Native tests use the real control code with an injected register/IIO backend.
They cover mute with missing radio attributes, busy timeouts, malformed payloads,
failed or ignored writes, rollback and rollback failure. Startup tests inject
radio and calibration failures and check that only a passing fast or fallback
profile marks the simulator ready.
The CGI must return an error while startup is pending or has failed. Motion tests
cover fractional accumulation, both reflection boundaries, long elapsed times,
pause/resume, window changes and edits that preserve other trajectories. Browser-model tests
cover queued edits, stale responses, mute during a write and failed retuning.
Shared fixtures check the exact scene payload in both Python and JavaScript.

`make test-web` starts and stops its own local preview and headless Chromium,
uses temporary profiles under `RTS_SCRATCH_DIR` (default `build/scratch`), and
writes logs/screenshots under `build/`. Set `CHROMIUM_BIN` if Chromium is not on
PATH. The test browser runs with its sandbox disabled and visits only the local
preview. It does not connect to Pluto or ESPARGOS. Python syntax and shell
syntax checks also run in `.github/workflows/tests.yml`.

Results from the clean-checkout test are recorded in
[validation/source-check.md](validation/source-check.md). More recent refactor and
second-device checks are in [software-refactor.md](validation/software-refactor.md). The GitHub workflow
uses the official [checkout](https://github.com/actions/checkout) and
[setup-python](https://github.com/actions/setup-python) actions.

## Testing the Pluto web interface

Install `requirements-hardware.txt`, system libiio and Chromium, then run:

```sh
python3 scripts/check_web.py --device http://192.168.2.1
```

The runner starts and stops an isolated browser, just like the preview test.
The live test expects 160 MSa/s by default. Set `RTS_EXPECTED_RATE=61440000`
to test fallback mode instead. It checks the reported mode, total-range axis
and shaded region below the minimum range.

This test changes the targets, radio gains and carrier frequency. Export the current
scene and record your radio settings first. It leaves targets muted, restores the
gains it initially read, but does not restore the original scene/carrier. It
checks the API and hardware readback, dragging, target visibility, axis-label zoom,
scene import/export and desktop/mobile layouts. It also checks that the legend
keeps its space and that clicking empty plot space leaves the scene alone.
Screenshots are in `build/device-web-{desktop,mobile}.png`.

## RF measurements with ESPARGOS

Install a compatible [pyespargos](https://github.com/ESPARGOS/pyespargos) checkout
and its dependencies. Set `PYESPARGOS_PATH` or pass `--pyespargos`; the default
looks for `../ESPARGOS/pyespargos` beside this project. Set `ESPARGOS_HOST` or pass
`--host` for your receiver. Set `PLUTO_HOST` or pass `--pluto` to select the Pluto in
measurement, MIMO-demo and sustained PN scripts. `config/lab.example.json` shows an example setup; the scripts do not load it
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
The optional native ADC snapshot tool specifically requires the unused reserved
DMA region from the original Maia-derived test image. It is not needed by the
radar simulator and cannot run against ordinary unreserved Linux memory.

`scripts/mimo_radar_pluto.py --host ADDRESS --pyespargos PATH` launches the existing
MIMO demo with a compatible 20 MSa/s waveform and expanded range. It reads the
Pluto carrier but does not modify the pyespargos sources. A wider displayed range
cannot remove the waveform's physical range ambiguity.

## Movement on Pluto

`PLUTO_URL=http://192.168.2.1 python3 tests/device_motion_check.py` exercises
four moving targets with different signed velocities, checks their measured rate
of travel and both bounce boundaries, then checks pause and stale-edit behavior.
It replaces the current scene and leaves all targets muted. Results are written
to `build/motion-live.json`. The live browser test also checks the movement toggle,
marker animation, axis-label wheel zoom, slider popovers, two-contact pinch zoom,
gain halos and the three-panel desktop layout.
