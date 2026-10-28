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
Range and velocity are independent controls: changing one doesn't move the other.

The plot shows monostatic range, calculated as
`c × (added delay + hardware latency) / 2`. Positive velocity means the target is
moving away, with `v = −c × Doppler / (2 × carrier)`. This matches the sign
convention in the ESPARGOS MIMO demo.

The UI includes the measured 0.325 µs hardware delay only when the FPGA version,
sample rate and filter bandwidth match the measured configuration. For other
configurations it shows range offsets, since the hardware delay is unknown.
All echoes come from the same antenna, so they have the same apparent direction.

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

The CGI checks request lengths, values, browser origin and gain steps. It shares
`/tmp/radar-control.lock` with `rtsctl` so simultaneous requests cannot interleave
register writes. Setting RX gain selects manual gain control. Gain changes leave
the targets, sample clock and filters alone. The driver reports the available
gain range, which can depend on the carrier. The API has no authentication.

The optional Python preview server has a separate JSON API under `/api/`.
Use the Pluto-hosted interface for the full set of radio controls. The
[register reference](registers.md) describes direct FPGA access.

## Scene files

An exported scene is a JSON object with `version: 1` and a `targets` array.
Each of its four possible entries has `enabled`, `delay_us`, `doppler_hz` and
`gain_db` fields. `delay_us` stores **added delay**, even though the plot shows
total range. The files in `config/` use the same format; the importer also accepts
files without a `version` field.

Scenes store target settings only. Carrier frequency, radio gains and plot zoom
are left as they are when you import a scene.
