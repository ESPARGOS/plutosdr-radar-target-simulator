# Testing

## Without hardware

Install Icarus Verilog, a C compiler, Node.js 18+, Chromium and the Python test
dependencies, then run the same checks as CI:

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-test.txt
make test-local test-native test-ui-model test-provenance test-release
make test-web
```

`make test-local` prepares the pinned ADI sources and tests the FPGA datapath,
fractional-delay response, sample-clock motion, AXI interface and control protocol.
`make test` runs that suite in the build container instead.

Native tests cover radio startup, API validation, failed writes and rollback.
UI tests cover scene conversion, queued edits, dragging, zoom and layouts.
Provenance and release tests check source/artifact matching and archive contents.

The browser test starts its own local preview and Chromium. Set `CHROMIUM_BIN`
if Chromium is not on PATH. Temporary profiles use `RTS_SCRATCH_DIR` (default
`build/scratch`), which should be a short absolute path because Chrome uses Unix
sockets. Logs and screenshots go in `build/`. The test disables Chrome's sandbox
and visits only the local preview.

## On a Pluto

Install `requirements-hardware.txt` and system libiio. Export your scene and
record the radio settings before running live tests: they change the device and
leave targets muted. They do not restore the original scene or carrier.

```sh
python3 scripts/check_web.py --device http://192.168.2.1
PLUTO_URL=http://192.168.2.1 python3 tests/device_motion_check.py
PLUTO_URL=http://192.168.2.1 python3 tests/device_mode_check.py
```

The browser check expects overclocked operation by default. Set
`RTS_EXPECTED_RATE=61440000` to check standard mode. The motion check exercises
four trajectories, reflections and pause/resume. The mode check switches radio
modes and verifies readiness and persistence.

Changes to the FPGA sample path also require a passing Vivado timing report
and RF validation. Compare commanded and measured delay and Doppler, check
clipping, and distinguish antenna feedback from simulator errors. The
[operating limits](limitations.md) describe these effects.

ESPARGOS acquisition and paper-analysis tests live separately in
[espargos-experiments](../espargos-experiments/README.md). They are not required
to build or test the simulator.
