# Architecture and controls

![Four parallel FPGA target paths](assets/fpga-datapath.svg)

All IQ processing runs in the FPGA. The ARM and browser only change settings.
Each target implements approximately
`y[k,n] = gain[k] × x[n − delay[k]] × exp(j × phase[k,n])`.
The four outputs sum with saturation to signed 16-bit IQ. The NCO has a 32-bit
phase accumulator and 10-bit phase lookup; amplitude coefficients are Q1.15.
The current target bank adds two RF logic-clock cycles after sample capture.

Added delay is an integer from 0 to 2047 samples. Fractional-sample delay is not
implemented. Changing delay can introduce a phase discontinuity; Doppler changes
preserve oscillator phase. An atomic commit flushes the short processing
pipeline. The browser updates during drag at approximately 12 commits/second.
Independent range and Doppler controls do not enforce physical kinematics.

Total monostatic range is `c × (added delay + hardware latency) / 2`. Positive
radial velocity means receding, using `v = −c × Doppler / (2 × carrier)` to match
the ESPARGOS MIMO demo. Only the qualified FPGA/rate/filter combination reports
the measured 0.325 µs offset; unmeasured profiles show range offsets instead.
All targets share one RF carrier and antenna direction. This cannot emulate
independent angles of arrival.

## Native HTTP API

BusyBox serves `/www`; `host/S61radar` copies embedded assets and the native CGI
there at boot. The API prefix is `/cgi-bin/radar.cgi`. Responses are JSON.
GET `/state` reports actual radio settings, FPGA capabilities and target state.
Writes are POST with `Content-Type: text/plain`:

| Endpoint | Body | Effect |
| --- | --- | --- |
| `/apply` | Enable mask, followed by four `delay_samples phase_increment gain_q15` rows | Atomically apply all targets |
| `/mute` | Empty | Clear every enable bit |
| `/radio` | Carrier frequency in Hz | Mute targets; tune RX and TX; verify readback |
| `/gain` | `rx 35` or `tx -25` | Set hardware gain; verify readback |

`phase_increment` is the unsigned 32-bit representation of signed
`round(Doppler / fs × 2^32)`; amplitudes are `0…32767`. The mask is `0…15`.
The CGI validates lengths, ranges, origin and gain steps, and serializes writes
with `rtsctl` using `/tmp/radar-control.lock`. RX gain edits select manual mode.
Gain changes preserve target settings, sample clock and filters. Driver-provided
gain limits can change with carrier. There is no authentication layer.

The optional Python server uses a separate JSON `/api/` protocol and is mainly a
preview/debug facility. The native device backend is the authoritative hardware
UI, including carrier/gain controls. See [registers](registers.md) for the FPGA ABI.

## Scene format

Export/import uses JSON with `version: 1` and a `targets` array of up to four
objects containing `enabled`, `delay_us`, `doppler_hz`, and `gain_db`. Scene
`delay_us` is **added delay**, even though the editor displays total range.
The example files in `config/` use the same target objects; the `version` field
is optional on import. Scenes do not store carrier, hardware gains or plot zoom.
