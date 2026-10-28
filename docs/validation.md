# Validation and limitations

The reference hardware is a Rev.B Pluto and ESPARGOS One with antennas separated
by roughly 5–10 cm. Results include this measurement chain, coupling and its
noise floor; they are not intrinsic transceiver specifications.

## Retained configuration

FPGA `0x00010010`, four targets, two-cycle target bank, multiplier-7 clock
conditioner and fast TX slew. RX/TX analog bandwidth stays at 20 MHz. The
160 MSa/s profile bypasses selected transceiver digital filtering while retaining
calibration and using driver-managed slow RX quadrature tracking (M=4).

At 2385 MHz the measured RF latency was **0.325 µs**. Four programmed added delays
of 0.5/1.5/3/4 µs appeared at 0.825/1.825/3.325/4.325 µs with the programmed
Dopplers. The peak grid is 6.25 ns; grid spacing is not absolute range accuracy.
See [zero-delay](validation/flashed-zero.json) and
[four-target](validation/flashed-four.json) summaries.

Two uninterrupted 600-second PN checks (RX and TX loopback) passed with all four
paths active, no errors and no clipping. See
[the long-check record](validation/160m-pn-600s-summary.json). Each normal boot
also runs native RX and TX checks before exposing ready controls.

The latest UI firmware was written, read back in full and rebooted. The
[manifest](validation/firmware-manifest.json), [startup record](validation/startup.txt)
and [browser regression](validation/browser-check.txt) identify that image.
The manifest is a historical release record, not a claim that subsequent source
cleanup changes have been rebuilt into it.

## Signal quality

The selected 160 MSa/s profile retained 20 MHz analog filtering. Final one-sided
broadband tests measured tagged SNR 31.07 dB normally and 31.79/31.54 dB in two
fast repeats, without clipping or ADC rail samples. See
[comparison](validation/qec-broadband-comparison.json).

Slow quadrature tracking improved isolated fast-profile RX image medians from
about −59 dBc to −63.90 dBc at low-band tones and −65.14 dBc near the band edge;
measurement floors were around −65 to −67 dBc. Native TX images were −52.07 dBc
fast and −53.30 dBc normally, at different native tone frequencies. See
[tracking comparison](validation/qec-comparison.json),
[RX images](validation/rx-sensitive-images.json) and
[TX images](validation/tx-sensitive-images.json).

These tests resolved no signal-quality degradation for the retained setup within
the measurement sensitivity. They do not prove exact equivalence for every
waveform, temperature, carrier or device. Raw NPZ captures remain in the local
`build/` archive and are not included in Git. Paths inside JSON records identify
those original captures, not public downloadable data.

## Limits

- 160 MSa/s is outside the AD9363's specified CMOS clock range. This is a
  qualified lab experiment on one device, not a manufacturer-supported profile.
- Radio fallback is 61.44 MSa/s. It does not inherit the 0.325 µs latency estimate.
- Do not independently change sample rate/FIR settings in the fast profile:
  the driver FIR cache and actual hardware bypass state differ. On Pluto,
  `radar-radio-fast restore` first returns to the normal muted profile.
- Four targets are retained. Three eight-target variants fit the FPGA resources
  but failed timing; none was loaded. Historical details are in the notebook.
- Delay is integer-sample only. No waveform prediction or fractional delay is used.
- Repeated radar waveforms introduce range ambiguity; slow-time accumulation sets
  the receiver's Doppler ambiguity. Plot zoom does not improve RF resolution.
- Antenna feedback may produce extra echoes or oscillation. The simulator cannot
  synthesize independent angles or calibrated radar cross sections.

See [the archived notebook](development-history.md) for rejected paths and detailed
measurement context. Earlier profiles in that notebook are not current defaults.
