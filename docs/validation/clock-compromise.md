# Interface clock, startup time and fallback

Measured on 30 October 2026 with the Rev.B Pluto at `192.168.2.1` and ESPARGOS
One at `172.16.0.241` using the existing antennas.

## Clock limit and minimum range

The [AD9363 datasheet, pages 6–7](https://www.analog.com/media/en/technical-documentation/data-sheets/AD9363.pdf)
specifies a maximum CMOS DATA_CLK of 61.44 MHz. Pluto uses that interface.
The 245.76 MHz LVDS limit is for a different electrical interface and does not
make 160 MHz CMOS operation supported. In this design, the complex sample rate
has the same numerical value as the interface clock.

The comparison used the current FPGA, a 2385 MHz carrier, 20 MHz analog bandwidth,
zero added delay and a 17 Hz Doppler tag. ESPARGOS received at 20 MSa/s. Each
capture lasted eight seconds after a muted baseline. Pluto used RX 25 dB,
TX −35 dB and −6 dB target gain. ESPARGOS used amplitude 0.4 and RX gain 25 dB.

| Configuration | Measured RF delay | Equivalent monostatic range |
| --- | --- | --- |
| 160 MHz, same test session | 0.3375 µs | 50.6 m |
| 61.44 MHz, normal filters | 0.78125 µs | 117.1 m |
| 61.44 MHz, receive HB1 bypass experiment | 0.74375 µs | 111.5 m |

The normal 61.44 MHz profile retains driver-managed half-band filters and keeps
the programmable FIRs bypassed. The extra filter bypass saved only 5.6 m and
has not had equivalent signal-quality testing. It is not used for fallback.

The existing 160 MHz UI reference is 0.325 µs, measured earlier on the first
Pluto. This session's 0.3375 µs result differs by two bins of the 6.25 ns analysis
grid. These are reference measurements, not per-device range calibration.
The 61.44 MHz UI reference is 0.78125 µs. Range is calculated as `c × delay / 2`.

An initial low-signal capture did not resolve the tagged echo reliably and was
excluded. Raw captures and plots remain in `build/clock-compromise/`. The useful
results and interface-check record are in [clock-compromise.json](clock-compromise.json).

## Shorter startup

Startup still scans RX/TX timing and finds the common input timing window.
Candidate checks now last one second, the TX test with live four-target updates
lasts five seconds, and the final RX check lasts one second. The first live run
completed in 27.7 seconds, down from about 124 seconds with the previous checks.
A separate 60-second RX check and 60-second TX-loopback check then passed without
errors while all four target paths were active.

Quick timing calibration has a 60-second retry budget at 160 MHz and a
90-second budget at 61.44 MHz. Timeout uses the checker's normal cleanup path.
Standard-mode calibration can take longer because its wider timing window has
more input taps to check. This shorter startup test detects failures observed
during its checks. It cannot establish long-term reliability for an interface
clock above the datasheet limit.

## Automatic fallback

Startup first tries 160 MHz. If calibration fails or times out, it restores the
normal clock and filter configuration and validates 61.44 MHz. Only a passing
profile starts the movement service and exposes editable controls. If both
profiles fail, targets remain muted.

Fallback is explicit in the API and the top-right status area. The radio panel
also labels the fallback sample rate, and the plot shades the unreachable
0–117.1 m region. Delay resolution changes to 16.28 ns, or 2.44 m, and the added
delay window grows to 33.32 µs. Realistic movement uses the actual sample rate.
A reboot tries the faster profile again.

A temporary checker wrapper deliberately rejected 160 MHz on the real Pluto.
The regular startup script then restored and validated 61.44 MHz. API readback
confirmed fallback, 20 MHz bandwidth, RX 25 dB, TX −35 dB and the changed latency.
The temporary wrapper was removed after the test. Native tests also cover both
profiles failing, and browser and movement tests exercise the fallback mode.

A second fault injection sent SIGALRM to the running fast-profile checker. It
restored the interface settings and the regular startup completed in fallback
mode. The temporary wrapper was removed afterward. Live browser and movement
checks passed at 61.44 MHz, and the ESPARGOS MIMO demo displayed all four targets
with no missing samples during the captured run.

## Installed firmware

The complete image was flashed to the second Pluto and verified by flash
readback. After reboot, the unmodified checker selected 160 MHz without
fallback. Radio startup took 27.6 seconds, and the API was ready 39.5 seconds
after the reboot command. Readback confirmed 20 MHz bandwidth, RX 25 dB,
TX −35 dB and the movement service running. The live browser regression passed
against the flashed image, including 1920×1080 layout, fallback-independent
controls, target dragging, pinch zoom and radio readback. Targets were left
disabled after testing.

Firmware SHA-256:
`96e0fc5fa2b5dbb4ed32d4abcd8bc88da7ca17c94fc4848a5c96d5e4c450afad`.
