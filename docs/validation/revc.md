# Rev.C Pluto checks — 30 October 2026

This check used a third Pluto at `192.168.2.1`, identified as Rev.C with a
Z7010 and AD9363. Its existing firmware already enabled the AD9361 driver
compatibility setting. The original flash contents were backed up before testing.

## Startup and interface timing

The first volatile load reached the 60-second fast-calibration timeout and
correctly recovered to 61.44 MSa/s. Both RX and TX loopback then passed separate
60-second checks with all four target paths active. Browser and movement checks
also passed in fallback mode.

A fresh 160 MSa/s setup with a longer, two-second candidate qualification found
working settings: RX delay register `0x0e`, TX `0xb4` and common FPGA input tap 14.
Separate 60-second RX and TX-loopback checks passed without errors at that rate.

Three further setups using the usual one-second qualification all passed. The
first started the FPGA input delay at tap 21, and the next two at tap 15. This
shows that the inherited input tap alone does not explain the initial failure.
No device-specific timing setting or relaxed acceptance check was added.

The complete firmware was then flashed and verified by readback. Three normal
reboots all selected 160 MSa/s without fallback, taking 45.75, 40.72 and 39.70
seconds from the reboot command to readiness. These were software reboots,
not power-cycle or temperature-sweep tests. The automatic 61.44 MSa/s fallback
remains available if fast calibration fails on a subsequent start.

The final live browser and four-target movement checks also passed against the
flashed image at 160 MSa/s. They covered dragging, radio readback, touch zoom,
desktop/mobile layouts and both movement boundaries. Targets were left muted.

## RF checks

The ESPARGOS MIMO demo at 2385 MHz and 20 MSa/s displayed all four simulated
targets, with 100% input coverage, no missing windows and about 4.9 dB estimated
receiver headroom. Pluto used RX gain 25 dB, TX gain −35 dB and target gain −14 dB.

An eight-second capture with zero added delay and a 17 Hz tag measured 0.3375 µs
receive-to-transmit delay, equivalent to 50.6 m. This matches the earlier
second-device measurement. It differs from the UI's 0.325 µs reference by two
bins of the 6.25 ns analysis grid. The UI reference is not per-device calibration.
This check establishes a working RF path, not a repeat of the original device's
full image-rejection and broadband-quality measurements.

The [machine-readable record](revc.json) includes firmware hashes, boot times,
interface status and RF measurements. Raw captures and detailed logs are kept
locally in `build/third-pluto/`. The image is built from this device's saved base
firmware, preserving its kernel, drivers and device trees.
