# Operating limits

## Minimum distance

The web interface includes a reference receive-to-transmit delay when converting
an echo's delay to distance. The reference is 0.45 µs in the faster mode and
1.35 µs in standard mode, corresponding to minimum distances of about 67.5 m
and 202.4 m. The wide overclocked profile uses 0.4140625 µs, or about 62.1 m.
Standard mode at 56 MHz uses 1.31875 µs, or about 197.7 m.
These are reference values, not individual calibration of your Pluto.
The shaded area below the minimum distance cannot contain targets.

Distances assume a radar that calculates range from the echo's round-trip time.
The spacing of the distance settings is not a guarantee of absolute accuracy.
Fractional-delay interpolation provides fine positioning. A manual jump to a
new distance can still change phase abruptly.

## Clock rate and bandwidth

The 160 MSa/s mode runs the radio interface above its specified 61.44 MHz limit.
Startup checks both receive and transmit operation before enabling the controls.
If the faster mode fails, the simulator tries 61.44 MSa/s. Both modes start with
20 MHz analog filters. A common RX/TX bandwidth can be adjusted up to 56 MHz in either
mode when the tuning range extension is enabled. Custom filter
combinations without a reference hardware delay display range offset rather than
total range. A startup check cannot guarantee
long-term stability at an overclocked rate.

Do not change the sample rate or radio filters through another application while
the simulator is running. Use the web interface for carrier frequency and gain
changes. For low-level work, `radar-radio-fast restore` first returns the radio
to the normal clock and filter settings with targets muted.

## What the echoes represent

The simulator supports four targets with independent delay, Doppler shift and
gain. All echoes leave the same antenna, so they have the same apparent direction.
Target gain controls echo amplitude, not a calibrated radar cross section.

Repeated radar waveforms can produce range ambiguity. The radar's waveform and
processing determine its distance and velocity resolution. Zooming the simulator's
plot changes the view, not that resolution. The maximum selectable delay can
exceed the radar's unambiguous range, in which case the echo appears at a
wrapped range in the radar display.

Coupling between Pluto's transmit and receive antennas can send a generated echo
through the simulator again. These extra echoes appear at sums of the configured
delays and Doppler shifts, possibly wrapped by the radar's unambiguous range or
velocity. Stronger feedback can cause oscillation. Clipping indicators do not
detect this effect, since feedback can occur well below the clipping level.

Reduce RX gain, TX gain or target gain, or improve isolation between Pluto's
antennas. A useful check is to lower TX gain and compare the responses: a repeated
echo falls faster than an intended echo because it passes through the transmit
path more than once. The appropriate gains depend on antenna placement and the
radar signal.

## Moving targets

Movement updates the fractional delay and carrier phase on every input sample.
It continues when the browser is closed. A target reflects at the minimum
distance or the upper edge of its movement window without restarting phase.

The model describes constant radial velocity between reflections. Instantaneous
reversals do not represent finite acceleration. Echo strength stays at the
configured gain rather than decreasing automatically with distance, and the
single transmit antenna cannot reproduce separate target angles.
