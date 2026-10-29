# Moving targets and axis controls — 29 October 2026

Tested on the second Rev.B Pluto at `192.168.2.1`, using the same FPGA and
160 MSa/s radio profile as the [timing-calibration check](160m-second-pluto.md).
The update adds an ARM movement service; it does not change the FPGA datapath.

## Movement

The live API test ran four targets at +75, +125, −175 and −225 m/s for five
seconds, with a 100-sample added-delay window. All four changed range, remained
inside the window and reversed Doppler sign at both boundaries. The 95th-percentile
position error between adjacent readbacks and the velocity-derived prediction
was 1.01 delay samples, including polling and scheduler timing.
This measures register behavior, not RF delay or signal quality.

The same test confirmed that stale scene values do not rewind trajectories,
disabling movement freezes the current range/Doppler, and mute remains effective
while the service is running. The test uses HTTP without a browser connected.

Native tests cover fractional accumulation at low speed, exact boundary hits,
multiple reflections over a long interval, pause/resume, narrowed windows and
external position edits. Controller tests check that editing one target does not
overwrite another moving trajectory. Startup tests cover movement-service failure.

## Interface

Live Chromium tests cover the movement toggle and marker interpolation, wheel
zoom on the axis labels, no zoom in the plot interior, the left-hand radio panel,
scene import/export and continuous drag/apply. Desktop checks include 1920×1080,
1920×900, 1536×760 and 1280×720; mobile checks use a 390-pixel viewport.

The desktop radio panel contains carrier, RX/TX gain, analog bandwidth/passband and
sample rate. Target settings remain on the right. The range and velocity sliders
now open in popovers when their underlined axis labels are clicked. Hovering an
axis label highlights it; wheel scrolling there zooms that axis. Tests also cover
two-contact pinch zoom, gain halos from −10 to −1 dB, matching visibility/movement
switches, and startup messages in the header.

The firmware image SHA-256 is
`29f93df8ea87c26ebdf6e26e93de74757cf6c74e78f1737bfb3046b9062d7f8a`.

## Reboot timing check

A later reboot selected common input tap 21 from an RX-good window of 20–22.
It passed RX but failed the sustained TX check, so startup correctly left the
simulator unavailable and muted. Calibration now retries other measured RX-eye
taps and qualifies both directions for each combination. It first tries four
interior TX candidates per input tap, then searches all TX candidates if needed.
The production code contains no fixed tap value for this device.

A test-only copy of the tuner deliberately preferred tap 21 when it was in the
measured RX-good set. TX failed the sustained check at that tap. The new retry
path then selected tap 20 and passed ten-second RX and TX checks at 160 MSa/s.
The fault injection is an ignored lab artifact, not part of the production tuner.

A subsequent 30-second check with moving targets caught another intermittent TX
error after 6.53 seconds at tap 21, despite a passing short startup check. The
final tuner therefore measures the intersection of the RX and TX input eyes,
centers that window, and checks TX for 60 seconds while continuously updating
all four targets' delay, Doppler and gain. It then rechecks RX at the selected
joint timing. This retains the full sample rate and does not bypass a checker.

The joint-eye test found taps 20–21 common to RX and TX and selected tap 20.
TX completed 60 seconds with live four-target delay/Doppler/gain commits, with
channel status `[0, 0]` and global status `1`. The following ten-second RX
recheck also passed. No checker errors were cleared during either interval.

The final image was flashed, read back and rebooted. It automatically selected
input tap 20, passed the 60-second live-update TX check and RX recheck, and started
the movement service at 160 MSa/s. A further 30-second check in each direction
with four independently moving targets also passed, with no PN errors or clipping.
See [the final PN summary](moving-targets-pn.json). Installed native tools and web
assets matched the local build hashes. The device was left at 2380 MHz, RX 0 dB,
TX −60 dB, with all targets cleared and muted.
