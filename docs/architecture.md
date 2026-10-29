# Signal processing and controls

![The four FPGA target paths](assets/fpga-datapath.svg)

The FPGA makes four copies of the received IQ signal. Each copy gets its own
delay, Doppler shift and gain:

`y[k,n] = gain[k] × x[n − delay[k]] × exp(j × phase[k,n])`

The four echoes are added together, clipped to the signed 16-bit output range,
and sent to the transmitter. Each oscillator uses a 32-bit phase accumulator
and a 10-bit lookup table. Gain coefficients use Q1.15 fixed-point arithmetic.
The target bank adds two RF clock cycles after sample capture. The ARM processor
and browser handle settings; they don't process the IQ samples.

## Delay, Doppler and range

You can add between 0 and 2047 whole samples of delay. Fractional-sample delay
isn't implemented. A delay change can cause a phase jump, while changing Doppler
preserves the oscillator's phase. Settings for all four targets take effect
together, and samples already in the short pipeline are discarded at that point.
While you drag a target, the browser sends updates about 12 times per second.
With Realistic movement off, range and velocity remain independent controls.

The plot shows monostatic range, calculated as
`c × (added delay + hardware latency) / 2`. Positive velocity means the target is
moving away, with `v = −c × Doppler / (2 × carrier)`. This matches the sign
convention in the ESPARGOS MIMO demo.

The UI includes the measured 0.325 µs hardware delay only when the FPGA version,
sample rate and filter bandwidth match the measured configuration. For other
configurations it shows range offsets, since the hardware delay is unknown.
All echoes come from the same antenna, so they have the same apparent direction.

Startup uses `radio-pn --tune` to select actual RX/TX clock/data delay pairs,
without relying on the driver's abbreviated timing scan. The test activates all
four target paths while checking the interface, then restores the saved scene.
RX prefers a valid data-only delay before trying clock-delay alternatives. It
then centers the common FPGA input-delay window, keeping data and frame timing
coherent. TX selects an interior passing point, then measures the intersection
of the RX and TX input-delay windows. The center of that joint window must pass
a 60-second TX check with live four-target updates, followed by another RX check.
Each candidate undergoes sustained PN checking,
and a failed candidate is excluded before trying another. If an FPGA input tap
passes RX but fails TX, startup tries the other measured RX-eye taps and checks
both directions again. It tries a few promising TX settings per input tap first,
then performs a full TX search if none passes. The checker uses the
shared control lock so a simultaneous scene request cannot change its test load.

## Moving targets

`radar-motion` runs on Pluto's ARM processor. Every 10 ms it advances enabled
moving targets using monotonic elapsed time, then commits changed delay/Doppler
words through the existing FPGA interface. It does not process samples or add RF
latency. Delay changes still use whole samples (about 0.94 m at 160 MSa/s), and
can introduce the same discontinuities as a manual delay change. This is not a
fractional-delay resampler or a sample-exact model of a moving reflector.

Positive radial velocity increases range. A target reverses velocity at either
end of the available interval: zero added delay and the current range window's
upper bound, rounded down to a whole delay sample. Fractional position is retained
between ticks so slow movement does not stall. Turning a target off or muting
pauses its motion; disabling movement freezes its current range and Doppler.
Shrinking the window clamps targets beyond its upper edge and sends them inward.
The window stays in effect when the browser closes. Scenes and motion state are
not restored across a reboot.

The service and CGI share the existing hardware lock. A small RAM-backed mapping
holds motion flags, bounds, fractional positions, readback and a heartbeat. A
scene request includes separate masks for explicitly edited positions and
Dopplers, so editing gain or another target does not rewind a moving trajectory.
The worker notices external register changes and rebases the corresponding
position. Raw `rtsctl apply` and legacy `/apply` requests disable motion.
A worker error mutes the targets; movement requests are rejected if its heartbeat
is stale. Normal scene controls and mute do not depend on the worker being alive.

The browser polls moving scenes more often and interpolates marker positions
between readbacks. This animation is display-only; the trajectory continues on
Pluto independently of browser timing. Ordinary target commits preserve NCO phase.

## HTTP API

At startup, `host/S61radar` copies the web files and CGI program into `/www`,
where BusyBox serves them. The API is under `/cgi-bin/radar.cgi` and returns JSON.
GET `/state` reads the radio settings, FPGA capabilities and targets. To change
settings, send a POST request with `Content-Type: text/plain`:

| Endpoint | Body | Effect |
| --- | --- | --- |
| `/apply` | Enable mask, then four `delay_samples phase_increment gain_q15` rows | Update all targets together |
| `/mute` | Empty | Disable all targets |
| `/radio` | Carrier frequency in Hz | Mute targets, tune RX and TX, and check the result |
| `/gain` | `rx 35` or `tx -25` | Set and read back the hardware gain |

The phase increment is `round(Doppler / fs × 2^32)`, encoded as an unsigned
32-bit word even for negative Doppler. Gain values run from 0 to 32767; the enable
mask runs from 0 to 15.

Movement-aware clients prepend one line to `/apply`:
`motion motion_mask position_edit_mask phase_edit_mask upper_delay_samples`.
Masks are 0–15 and the upper bound is 1–2047. The remaining body is the same scene
format. An unset edit bit preserves that field for an already-moving target;
new targets must set both edit bits. `/state` exposes `motion_available`,
`motion_upper_samples`, and each target's `realistic_movement` flag.
Legacy requests remain supported and turn movement off.

The CGI checks request lengths, values, browser origin and gain steps. It shares
`/tmp/radar-control.lock` with `rtsctl` so simultaneous requests cannot interleave
register writes. Setting RX gain selects manual gain control. Gain changes leave
the targets, sample clock and filters alone. The driver reports the available
gain range, which can depend on the carrier. The API has no authentication.

Mute only needs the FPGA register map. It still works when the sample clock,
carrier or gain attributes cannot be read. In that case the response confirms
`muted: true`, returns `null` for unavailable values and includes a warning.
Carrier changes leave targets muted on both success and failure. Failed gain or
carrier writes attempt to restore the previous settings and verify the result.

The Python preview uses the same scene payload under `/api/`; only the endpoint
prefix differs. It does not expose carrier or radio-gain controls. The
[register reference](registers.md) describes direct FPGA access.

## Software layout

`host/radar_control.c` implements scene validation, register commits, gain
changes and tuning. Both the command-line program and CGI link it normally.
Its small I/O interface separates those operations from Linux: `radar_linux.c`
provides the memory mapping, shared lock and IIO attributes, while the tests
supply an in-memory backend that can fail individual reads and writes.

The browser uses native JavaScript modules, without a bundler:

- `scene.js` validates scenes and converts physical units to register values.
- `api.js` handles HTTP requests, errors and timeouts.
- `controller.js` owns the scene and serializes all device requests. It combines
  rapid edits, ignores stale scene readbacks and cancels unsent edits before mute
  or retuning, so an old update cannot switch targets back on.
- `plot.js` handles plotting, dragging and zoom. `app.js` connects the controls
  to the scene controller; `dom.js` contains the small DOM helpers.

`host/server.py` serves the hardware-free preview. `host/control.py` provides
its in-memory state and the SSH adapter used by measurement scripts.
`host/scene.py` shares the Python conversion rules. Golden payload fixtures
check that Python and JavaScript agree, including negative and half-step rounding.

Startup publishes readiness only after the 160 MSa/s timing calibration and PN
checks pass. Until then, the CGI returns HTTP 503. A failed startup leaves targets
muted and reports the failure; recovery clocks do not enable a slower simulator.

## Scene files

An exported scene is a JSON object with `version: 1` and a `targets` array.
Each of its four possible entries has `enabled`, `delay_us`, `doppler_hz` and
`gain_db` fields. `delay_us` stores **added delay**, even though the plot shows
total range. The files in `config/` use the same format; the importer also accepts
files without a `version` field.

Scenes store target settings only. Carrier frequency, radio gains and plot zoom
are left as they are when you import a scene.
