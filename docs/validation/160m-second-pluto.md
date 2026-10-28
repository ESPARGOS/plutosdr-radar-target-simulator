# 160 MSa/s startup on the second Pluto — 28 October 2026

The initial fallback to 61.44 MSa/s was a timing-calibration problem. The FPGA
configuration payload was unchanged from the earlier RF-tested build.

The ADI driver's abbreviated scan found an RX window but failed TX tuning and
restored the normal-rate delay values. A full scan found working RX/TX pairs,
but the default FPGA input delay of 21 taps still produced intermittent TX
loopback errors under four-target load. A short passing check was insufficient.

The corrected startup scans actual clock/data pairs, centers the common FPGA
input-delay window and qualifies candidates with all four target paths active.
It checks RX and TX separately and rejects candidates that produce errors.
Keeping the data and frame delays coherent worked better here than centering
individual lanes against RX BIST alone. No arithmetic pipeline or radio filter
was added, and no check was bypassed.

## Working configuration

- Sample rate: 160 MSa/s; analog bandwidth: 20 MHz.
- AD9363 RX delay register: `0x0b`; TX delay register: `0xb4`.
- All thirteen FPGA receive-input delays: 20 taps.
- Independent five-minute RX and TX tests passed with zero errors and all four
  FPGA target paths active. Sticky checker errors were not cleared during either
  measurement interval.
- After flashing, a further five-minute RX test followed by a five-minute TX
  loopback test also passed with all four paths active and no checker errors.
- A fresh FPGA load and driver initialization selected these settings
  automatically and passed startup qualification.
- The firmware was then flashed with checksum/readback verification and booted
  successfully at 160 MSa/s. The test image uses this device's own DICHASUS base,
  not the first Pluto's Maia-derived base.

The range display therefore uses the existing measured 160 MSa/s profile again:
0.325 µs and a shaded minimum range of about 48.7 m. This work verified digital
interface integrity; it did not make a new RF latency measurement on this unit.

## Firmware and compatibility

The device does not require Maia SDR. The remaining references identify the
build-container publisher, optional cleanup for Maia-derived base images and a
lab-only ADC capture tool that uses an old reserved-memory layout.

The old DICHASUS init script ignored its `stop` argument and started
`maia-reftx` during shutdown, blocking reboot. Deployment now moves that script
out of the init directory in RAM. Packaging removes its startup entry from the
new image. The original firmware partition backup is retained for recovery.

Startup now requires successful 160 MSa/s calibration. Tests cover radio setup
failure, both calibration failure exits and the API response: none publishes a
ready simulator. Recovery to normal clocks leaves targets muted and unavailable.
Timing values are selected from measurements on each boot, not copied from this
unit. This validates a second Rev.B device; it does not establish compatibility
with every Pluto revision or guarantee timing across voltage and temperature.

## Final image and UI checks

The final image was flashed and read back, then booted with the required-rate
startup behavior. It selected RX `0x0b`, TX `0xb4` and input tap 20 automatically.
The input scan on this boot found two clean taps (20–21), compared with four in
an earlier run; the selected setting still passed both sustained startup checks.

- Firmware: `build/firmware/second-pluto/pluto.frm` (13,331,420 bytes).
- SHA-256: `5b027ad2483aedf0976e4d80d3c5fd3185625f22b97758051677fd7e07e5953e`.
- Live browser regression: passed, including 160 MSa/s readback, the shaded
  unreachable range, target dragging and continuous apply, gain/carrier changes,
  scene import/export, and desktop/mobile layouts.
- After the browser tests retuned the carrier and changed gains, a further
  60-second check in each direction passed with all four targets active and no
  checker errors. The device was left at 2380 MHz, RX 0 dB, TX −60 dB, muted.
- Native control, CGI, startup failure, scene-model and provenance tests passed,
  including a clean extraction of the staged source.
- [Sustained PN results](160m-second-pluto.json) retain the checker status and
  active target settings from the five-minute tests in each direction.

The original Pluto at `192.168.4.1` was unreachable during this final check. The
new calibration code therefore still needs a cross-check on that unit, as well
as testing on other revisions, before claiming broad hardware compatibility.
