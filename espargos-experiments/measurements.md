# Measurement details

## Acquisition and processing

`scripts/measure_espargos.py` records raw IQ, waveform pilots, snapshot timestamps,
radio settings, target settings and movement readback. It first captures a muted
reference, then enables the requested scene. It mutes both devices on exit.

The `range` recipe uses 10 MSa/s and 1024-sample vectors. Its reference is a
separate single-echo recording. `analyze_measurement.py` uses that reference for
receive combining and computes the delay–Doppler map. The plot uses one power
normalization, referenced to the strongest intended echo. Each display cell takes
the maximum of its analysis bins to preserve narrow peaks at print size.

The `trajectory` recipe uses 20 MSa/s and 512-sample vectors with 240 odd-bin
pilots. Their 78.125 kHz spacing avoids an interior DC gap. One constant phase per
receiver comes from an independent 16-second reference. Analysis uses two-second
windows at one-second steps. Range/time maximizes over Doppler; velocity/time
maximizes over a fixed 60–500 m interval. Programmed trajectories do not enter
these power calculations. The figure uses a 0.4140625 µs hardware-delay reference.

`analyze_delay_sweep.py` fits relative delay from the subcarrier phase slope.
The first position is the reference. The five sweeps return to zero at the end
and use no drift correction. `analyze_motion.py --bandwidth 5` processes the
30-second two-tone recordings with identical analysis filters. These measurements
include RF phase noise and propagation effects.

`analyze_feedback.py` locates the primary and repeated echoes in the strongest
TX-gain segment and keeps those range windows fixed across the sweep. The plot
includes windows where both echoes exceed the local noise estimate by 6 dB.
Markers are medians, error bars are interquartile intervals. The linear-feedback
prediction has unit slope with only its offset fitted. The second sweep halves
the radar source amplitude. Lower gain or better antenna isolation suppresses
feedback, but also changes its visibility in the measurement.

## Whole-sample comparison helper

From this directory, build the optional helper using the project's Docker/Vitis
setup, then copy it to Pluto:

```sh
make motion-baseline-tool
scp build/radar-integer-baseline root@"$PLUTO_HOST":/tmp/radar-integer-baseline
```

`/tmp` here is Pluto's volatile filesystem. The helper rounds delay at 100 Hz
while preserving carrier phase. `--integer-motion-baseline` selects it in the
recorder. Ordinary fractional motion continues to run on the FPGA. The helper
has a 120-second timeout and captures are limited to 110 seconds.

## Additional diagnostics

The other `analyze_*.py` tools cover ADC images, two-tone distortion, raw spurs,
noise, tone turn-off envelopes and wideband response. Run each with `--help`.
A wideband echo/direct-path ratio includes antennas and propagation, so it does
not isolate the simulator's intrinsic passband.

Native ADC snapshots are optional. `make capture-tool` builds `radio-capture`,
which must be installed at `/tmp/radio-capture` on Pluto. It requires a compatible
reserved DMA region as checked by `host/radio_capture.c`; ordinary Linux memory
cannot be used. The paper recipes do not require this diagnostic.

Raw files can contain local paths and device information. Keep them in the ignored
`build/` directory. The public recipes contain no device addresses or serial numbers.
