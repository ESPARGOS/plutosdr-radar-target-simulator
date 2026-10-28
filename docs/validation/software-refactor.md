# Software refactor validation — 28 October 2026

The CLI and CGI now share the native control library. The browser separates
scene conversion, HTTP requests, queued updates and plotting. The Python preview
accepts the same register payload as the device. Abandoned FPGA variants, their
tests and one-off tuning scripts were removed; Git history retains that work.

## Checks

- HDL: 15,000 reference-model clocks, AXI/CDC/mute tests and 1,000 ADI interface
  samples passed in the pinned build container.
- Native: strict compilation, missing IIO attributes, busy timeouts, malformed
  requests, write/readback failures and rollback tests passed.
- Browser model: eight queue tests and five scene/API tests passed. Python and
  JavaScript matched the shared register-payload fixtures.
- Provenance: changed or added sources, substituted artifacts and a missing
  manifest were rejected.
- Synthetic RF-analysis tests and the isolated preview browser test passed.
- The live UI passed scene/gain/carrier readback, continuous dragging, mute,
  import/export, zoom and 1920×1080, 1920×900, 1280×720 and mobile layout checks.

## Second Pluto

Testing used a second Rev.B Pluto running DICHASUS firmware at `192.168.2.1`.
Its firmware partition was backed up before stopping `maia-reftx`. The FPGA,
control programs and web files were loaded into RAM; flash was not changed.

The 160 MSa/s PN check failed on this unit. Startup restored 61.44 MSa/s and
passed both normal-rate interface checks, with targets muted. Live UI/API tests
used that verified profile. The interface correctly showed range offsets rather
than claiming a measured hardware delay for this configuration. No new RF
latency or signal-quality measurement was made in this software refactor.

This driver reports TX gain availability as `[-89.750000]`. The control library
recognizes that exact response and uses the fixed −89.75…0 dB, 0.25 dB-step TX
range described in [ADI UG-570, transmit power control](https://www.analog.com/media/en/technical-documentation/user-guides/ad9361.pdf).
Other malformed or missing limits still produce an error. Hardware gain writes
and readback passed on the device.

The test interface was left available at `http://192.168.2.1/`, with 2380 MHz,
RX 0 dB, TX −60 dB and all targets muted. A reboot restores DICHASUS.

## Build artifacts

A clean Vivado implementation met timing. Its configuration payload is
byte-identical to the previously RF-tested build; only the `.bit` header differs.
This is not a new datapath implementation.

| Artifact | SHA-256 |
| --- | --- |
| Fresh `system_top.bit` | `a091964abb3636b7e2826f02b56ece3c8713a54edb1e913cecbdfed79bed3d66` |
| Configuration payload, old and fresh builds | `d0291d82a950462937efef4c1c44ed0e90c20c1dc796baa688bf85f47f13232b` |
| Rebuilt `pluto.frm` | `cca16a9444afefea6534404b2165ecf9ba36e6d8a7c42e87feb0b48377163daf` |

The firmware was packaged from the original compatible Maia base. It was not
flashed to either device during this refactor. Full source/toolchain/input hashes
are in the generated `build/fpga-manifest.json`, `build/tools-manifest.json` and
`build/firmware/firmware-manifest.json`. These generated files stay out of Git.

The initial 160 MSa/s fallback described here was subsequently fixed by
[timing calibration on the second Pluto](160m-second-pluto.md).
