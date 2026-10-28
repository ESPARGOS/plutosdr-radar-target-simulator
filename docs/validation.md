# Measurements and limitations

These measurements used a Rev.B Pluto and an ESPARGOS One, with their antennas
about 5–10 cm apart. The results include antenna coupling and the ESPARGOS
receiver's noise floor, so they describe the complete setup.

## Hardware configuration

The tested FPGA (`0x00010010`) has four targets and a two-cycle target bank.
It uses a multiplier-7 clock conditioner and the fast TX slew setting. RX/TX analog bandwidth stays at 20 MHz. The
160 MSa/s profile bypasses selected transceiver digital filtering while retaining
calibration and using driver-managed slow RX quadrature tracking (M=4).

At 2385 MHz the measured RF latency was **0.325 µs**. Four programmed added delays
of 0.5/1.5/3/4 µs appeared at 0.825/1.825/3.325/4.325 µs with the programmed
Dopplers. The peak grid is 6.25 ns; grid spacing is not absolute range accuracy.
See [zero-delay](validation/flashed-zero.json) and
[four-target](validation/flashed-four.json) summaries.

Two uninterrupted 600-second PN checks (RX and TX loopback) passed with all four
paths active, no errors and no clipping. See
[the long-check record](validation/160m-pn-600s-summary.json). The startup script
also checks RX and TX before making the controls available.

The latest UI firmware was written, read back in full and rebooted. The
[manifest](validation/firmware-manifest.json), [startup record](validation/startup.txt)
and [browser regression](validation/browser-check.txt) identify that image.
Those records describe the flashed image. Later source and documentation edits
are not included in that image unless it is rebuilt.

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

We found no signal-quality degradation that these tests could resolve. That
result is limited to the waveforms, device and conditions measured here. The raw
NPZ captures are kept locally under `build/`; paths in the JSON summaries refer
to those files, which are not included in the repository.

## Limits

- 160 MSa/s is outside the AD9363's specified CMOS clock range. The measurements
  cover one device; this clock rate is not supported by the manufacturer.
- Radio fallback is 61.44 MSa/s. It does not inherit the 0.325 µs latency estimate.
- Do not independently change sample rate/FIR settings in the fast profile:
  the driver FIR cache and actual hardware bypass state differ. On Pluto,
  `radar-radio-fast restore` first returns to the normal muted profile.
- The design supports four targets. We tried three eight-target variants; all
  fitted in the FPGA but failed timing, so we did not load them. Historical details are in the notebook.
- Delay is integer-sample only. No waveform prediction or fractional delay is used.
- Repeated radar waveforms introduce range ambiguity; slow-time accumulation sets
  the receiver's Doppler ambiguity. Plot zoom does not improve RF resolution.
- Antenna feedback may produce extra echoes or oscillation. The simulator cannot
  synthesize independent angles or calibrated radar cross sections.

See [the archived notebook](development-history.md) for rejected paths and detailed
measurement context. Earlier profiles in that notebook are not current defaults.
