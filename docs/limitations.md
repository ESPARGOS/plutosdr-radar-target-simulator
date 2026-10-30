# Operating limits

## Minimum distance

The web interface includes a reference receive-to-transmit delay when converting
an echo's delay to distance. The reference is 0.325 µs in the faster mode and
0.78125 µs in fallback mode, corresponding to minimum distances of about 48.7 m
and 117.1 m. These are reference values, not individual calibration of your Pluto.
The shaded area below the minimum distance cannot contain targets.

Distances assume a radar that calculates range from the echo's round-trip time.
The spacing of the distance settings is not a guarantee of absolute accuracy.
Delay changes use whole samples and can introduce phase discontinuities.

## Clock rate and bandwidth

The 160 MSa/s mode runs the radio interface above its specified 61.44 MHz limit.
Startup checks both receive and transmit operation before enabling the controls.
If the faster mode fails, the simulator tries 61.44 MSa/s. Both modes retain
20 MHz analog bandwidth. A startup check cannot guarantee long-term stability
at an overclocked rate.

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
plot changes the view, not that resolution.

Coupling between Pluto's transmit and receive antennas can create extra echoes
or oscillation. Reduce gain or improve antenna isolation if this occurs. The
appropriate gain settings depend on antenna placement and the radar signal.

## Moving targets

Movement updates distance 100 times per second, rounded to whole delay samples.
It runs on Pluto even when the browser is closed. A target reverses direction at
the minimum distance or the upper edge of the selected range window. This is a
simple motion model, not a continuous fractional-delay simulation.
