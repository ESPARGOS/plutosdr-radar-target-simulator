# Historical FPGA experiments

These alternatives were used while investigating latency and timing. They are
not selected by `make prepare`, `make fpga` or firmware packaging. Their filenames
describe candidates, not supported modes. Some failed timing or RF quality checks.

The retained implementation is in `rtl/` plus `patches/`; its qualification is
summarized in `docs/validation.md`. Candidate-specific test scripts remain in
`tests/` for research reproducibility. Run them explicitly and keep candidate
builds separate from the validated vendor tree. Do not load an experimental image
without checking its own timing report and completing hardware qualification.
