# Startup feedback and default gains

Tested on 30 October 2026 with the Rev.B Pluto at `192.168.2.1` and the
ESPARGOS One at `172.16.0.241`, using antennas in the existing bench setup.

The startup timings here describe the earlier, longer checks. See
[the clock comparison](clock-compromise.md) for the shorter checks and automatic
61.44 MHz fallback added afterward.

## MIMO radar visibility

The test used the actual `MIMORadar` setup, calibration and capture methods from
`pyespargos/demos/iq/mimo-radar/main.py`, followed by its `MIMOProcessor.maps()`.
It kept the demo's normal TX amplitude of 0.4 and RX gain of 25 dB, with
2385 MHz carrier, 20 MSa/s receive rate and a 600 m range window.

With the previous simulator defaults of RX 0 dB, TX −60 dB and target gain
−18 dB, the three test locations were only 3–6 dB above the demo's estimated
background. They were below its normal 12 dB display floor. RX 25 dB and
TX −35 dB brought the same targets to about 25–26 dB with −12 dB target gain.

The selected defaults use −14 dB per target. Four targets then have a combined
amplitude gain below one, and all four remained visible in three repeated
captures using the editor's default positions:

| Target | Configured range | Configured velocity | Peak range | Peak velocity | Peak above display background |
| --- | --- | --- | --- | --- | --- |
| 1 | 159.3 m | −0.90 m/s | 160 m | −0.91 m/s | 23.1–23.6 dB |
| 2 | 258.6 m | +0.90 m/s | 260 m | +0.91 m/s | 23.1–23.6 dB |
| 3 | 357.9 m | −1.65 m/s | 360 m | −1.64 m/s | 23.2–23.6 dB |
| 4 | 456.2 m | +1.65 m/s | 460 m | +1.64 m/s | 22.3–23.0 dB |

ESPARGOS reported about 5.2 dB of ADC headroom. The FPGA clipping flag stayed
clear. These measurements establish visibility in this demo and antenna setup,
not calibrated RF power, radar cross section or a universal gain setting.
The dB values use the demo's background estimate, not a separate noise-figure
measurement. Raw maps and the temporary measurement harness remain in
`build/defaults/`. The compact results are in
[startup-and-defaults.json](startup-and-defaults.json).

## Startup

The FPGA is loaded before the radar init service runs. Most of the roughly
two-minute wait is radio interface calibration and integrity checking. The
service now publishes its current stage and boot-relative elapsed time without
requiring the CGI to acquire the FPGA lock. It distinguishes timing scans,
shared timing checks, the 60-second TX test, RX checks and movement-service
startup. Failed startup retains the last stage and leaves controls unavailable.

Operating gains are applied only after calibration succeeds. During calibration,
TX remains at −60 dB. The simulator still starts with no active targets.

Native tests cover valid, missing and malformed progress records, startup
failure and success, and browser recovery from startup to a usable state.

The flashed firmware completed radio startup in about 124 seconds, or 136 seconds
from the reboot request. HTTP progress remained available during calibration.
RX and TX checks passed at 160 MSa/s. Readback confirmed RX 25 dB, TX −35 dB
and a nominal 2385 MHz carrier (the PLL readback was 2 Hz below the request).
Live browser checks also passed for startup feedback, controls and screen layouts.

A final run used the demo's unmodified worker and a shader-capable virtual
display. Its range–Doppler plot showed all four targets, with 100% input coverage,
no missing windows and about 12 plots per second. The screenshot is retained
in `build/defaults/mimo-demo.png`. The devices were muted after testing.
