# Earlier FPGA designs

These are the designs we tried while reducing latency. The normal build uses
`rtl/` and `patches/`; it does not select anything in this directory. Some of
these alternatives failed timing or signal-quality tests.

The matching tests are still in `tests/` if you want to revisit an experiment.
Use a separate build tree, check its timing report, and test it on hardware
before treating it as a working replacement. Results for the current design
are in [the measurement notes](../docs/validation.md).
