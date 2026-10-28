# Contributing

The guides in `docs/` describe the current design. Earlier experiments remain
in Git history.

For software changes, run `make test-native test-ui-model test-provenance`,
`make test-local test-analysis` and the relevant browser test. You can use `make test` to run the HDL tests in Docker instead.
[The testing guide](docs/testing.md) explains the dependencies and hardware tests.
Save your scene and radio settings before running tests against a Pluto; those
tests change both. CI runs without hardware.

Changes to the sample path need more checking. Run the bit-exact simulation and
check the final Vivado timing report before trying a new bitstream. Changes to
clocking or the radio interface also need RF measurements. When reporting latency
or signal quality, include the sample rate, analog bandwidth and measurement
setup so others can compare the results.

Keep generated files in `build/` and temporary files in `RTS_SCRATCH_DIR`. Vendor
checkouts, tool installations, firmware backups, credentials and raw captures
should stay out of Git. Small measurement summaries belong in `docs/validation/`.
For firmware releases, include a checksum, source revision and the notices and
source materials required by the bundled components' licenses.

Use `.clang-format` for C and Black for Python. The web source uses Prettier;
`npm install` followed by `npm run format:web` runs the pinned development tool.
The UI itself has no npm runtime dependency or build step. Keep tests focused on
observable behavior and remove abandoned experiments once their conclusions are
recorded.

In a pull request, explain what changed, why, and how you tested it.
