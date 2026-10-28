# Contributing

Use the current guides in `docs/`; the development notebook records historical
experiments and must not be treated as a sequence of current setup instructions.

Keep the real-time datapath in FPGA logic. Changes to delay arithmetic, NCOs,
clocking or the AD9363 interface require the bit-exact oracle, final Vivado timing
checks and new hardware qualification. Never deploy a timing-failing experiment.
Document the sample rate, analog bandwidth, reference measurement and limits of
any latency/quality claim.

For software changes, run `make test-local`, `make test-analysis`, and the relevant
browser check. `make test` uses the container instead of host Icarus. See
[testing](docs/testing.md) for dependencies and explicit hardware tests. Ordinary
CI never flashes hardware or transmits RF. Device/browser tests alter scenes and
radio settings; save the current scene before running them.

Do not commit vendor sources, AMD installations, firmware backups, credentials,
SSH host-key files or raw captures. Put generated artifacts under `build/` and
scratch files under `RTS_SCRATCH_DIR`. Keep small, clearly attributed validation
summaries in `docs/validation/`. Firmware binaries belong in release assets, with
checksums, the corresponding source revision and applicable third-party notices.

Describe the behavior change, affected FPGA/radio profile and verification in
pull requests. Historical alternatives live in `experiments/`; adding a candidate
there does not qualify it for the default build.
