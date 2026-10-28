# Source preparation check — 2026-10-28

The GitHub preparation was checked without changing the running FPGA or radio.

- A clean source archive was extracted into a new local Git repository.
- `make test` fetched the pinned ADI HDL revision, applied patches, generated the
  ROM, and passed the 15,000-clock oracle, AXI/CDC, control, firmware-import and
  patched-interface regressions in the pinned build container.
- Prepared `.v`, `.sv`, `.xdc`, `.tcl` and `.mk` sources matched the existing vendor
  tree used for the validated firmware. There were no differences.
- `make test-analysis` passed synthetic range/Doppler, signal-quality, raw-spur,
  ADC-image and native-TX-image checks.
- `make test-web` passed the updated hardware-free preview test, including default
  enabled targets, joined On/Off, total-range edits, automatic apply, dragging,
  mute and mobile width. The isolated browser and server exited afterward.
- Python compilation, shell syntax, local Markdown links and Git whitespace checks
  passed. The source set excludes vendor/build trees and firmware/capture files.
- The SVG block diagram was rendered and visually inspected.

The GitHub Actions workflow is configured but has not run on GitHub yet.
No new FPGA synthesis, firmware flash or RF qualification was needed for these
source/documentation changes; the installed reference remains the image in
`firmware-manifest.json`. The full local logs are under `build/project-cleanup-*`.
