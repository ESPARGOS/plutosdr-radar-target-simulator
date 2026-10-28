# Development history

Archived lab notebook, retained for provenance. Statements about “current”,
“installed” or “ongoing” describe the time of each experiment, not today’s build.
Use the top-level README and current guides for operation. `build/` paths below
refer to private local evidence, deliberately excluded from Git.

# PlutoSDR Target Studio

Four simultaneous radar echoes, processed entirely in the Pluto's Zynq FPGA.
A web application hosted directly on Pluto controls added delay, signed Doppler, amplitude and
individual enable state. It never transports IQ samples through the host.

## Web controls

The plot and range editor show **total range**, including the measured 0.325 µs
RF latency (minimum approximately 48.7 m). The sidebar shows total delay in µs
and Doppler in Hz. Range uses the monostatic convention, c × total delay / 2.
Scene files and the control API retain added `delay_us`, so existing scenes stay
compatible. An unmeasured radio profile explicitly shows range offsets instead.

The horizontal axis is **radial velocity** and the vertical axis is **total range**.
Zero velocity always stays centered. Range windows start at zero, with the
unachievable 0–48.7 m region shaded and blocked for placement. Velocity zoom stays
symmetric about zero. Continuous logarithmic sliders set both view limits; the
mouse wheel zooms only the selected slider panels (range, velocity, both, or
neither). Click a panel’s label or border to select it. Zooming never
changes target settings. Off-screen targets are marked in the
list; selecting one reveals it, expanding the symmetric velocity window when
needed. **Fit targets** shows the whole scene.

All edits and scene imports apply automatically; there is no manual-apply mode.
Dragging preserves the pointer's grab offset, ignores small click movements, and
updates the FPGA during the drag (throttled to approximately 12 updates/second),
with a final update on release. Dragging into the shaded range clamps at the
hardware minimum. Targets are created only with **+ Add target**; clicks in empty
plot space do nothing. Legend space remains reserved even with no targets. Carrier edits apply on
commit/blur and mute the scene during tuning. Import and export are alongside
the target controls. The favicon is from ESPARGOS controller firmware.

The ESPARGOS-styled interface uses larger local Carlito text and a joined On | Off
control for each target. New targets start enabled. RX and TX hardware gain controls apply automatically,
using the radio driver’s carrier-dependent limits and step sizes. RX edits select
manual gain control; TX gain is expressed in dB (negative values mean attenuation).
Gain changes preserve the target scene, sample rate, and filters.

The radio summary distinguishes **20 MHz analog RF bandwidth** (approximately
2375–2395 MHz at a 2385 MHz carrier, with gradual filter roll-off) from the
**160 MSa/s digital sample rate**. It reads actual RX/TX bandwidth from the device.
Sample rate remains read-only because changing it requires radio reconfiguration
and latency validation.

The complete desktop layout has been checked at 1920×1080, 1920×900, 1536×760,
and 1280×720, including all targets and the open inspector, with no page scrolling.
Mobile has a separate responsive layout. Four targets remain the validated FPGA
limit; ten would require FPGA changes and fresh timing/RF qualification.
Live gesture/readback, scene round-trip, favicon, bandwidth, and layout evidence
is in `build/ui-radio-gains/`, including gain validation and hardware readback,
alongside screenshots and firmware digests.

## Eight-target feasibility experiment

Eight targets fit the Zynq-7010: the first implementation used 48/80 DSP blocks,
30/60 block RAM tiles, and 7,434/17,600 LUTs. The eight-path bit-exact oracle
passes 15,000 clocks, including signed Doppler, independent delays, reloads,
clipping, mute, and sample gaps; upper-target AXI/CDC register checks also pass.

However, three implementations failed the unchanged 160 MSa/s timing constraints:
two, three, and four pipeline cycles had final setup slacks of −0.700, −0.039,
and −0.075 ns. Additional physical optimization did not qualify the three-cycle
version. The four-cycle version moved the remaining critical paths into NCO
coefficient addressing and preparation controls. No failed image was loaded.
The installed firmware retains four targets and its measured 0.325 µs latency.
Eight targets need further timing work (or a separately qualified lower-clock
profile) and live RF validation. Sources, reports, and results are archived in
`build/eight-targets/results.json` (local `build/eight-targets/`); the isolated working
checkout is under `$RTS_SCRATCH_DIR/eight-targets`.

## Installed latency profile

The two-cycle FPGA (`0x00010010`) measured **0.325 µs** RF latency at 160 MSa/s,
with the original 20 MHz analog bandwidth. This is a causal receive/retransmit
path for arbitrary samples; no repeating-waveform prediction or display offset
is used. Four simultaneous programmed delays of 0.5/1.5/3/4 µs appeared at
0.825/1.825/3.325/4.325 µs, with Dopplers −31/−17/+17/+31 Hz. See
`build/latency-round4/output-hold/flashed-zero.json` (local zero-delay measurement) and
`build/latency-round4/output-hold/flashed-four.json` (local four-target measurement).
The peak-estimation grid is 6.25 ns; these numbers are not an absolute timing
accuracy specification. The all-in-one image has been flashed, fully read back,
rebooted, and revalidated over RF at 2385 MHz. The Pluto-hosted browser controls
also passed desktop/mobile tests. Original carrier, gains, and four muted targets
have been restored.

`build/firmware/pluto.frm` (local Installed firmware), SHA256:
`2d381f503f6a1243ac751d1648b87241d11eb876c4ba1cda72d004cb5055b663`.
Boot, flash, browser, and restored-state records are in
`build/latency-round4/output-hold/` (local `build/latency-round4/output-hold/`).

The diagnostic direct path, which has no target bank, measured about 0.306 µs
with the same 20 MHz filters. Thus only about 19 ns of the current measured
delay is attributable to adding the general four-target path. One-cycle DSP,
carry-save, and reduced-fanout variants preserved the arithmetic in simulation
but failed implementation timing; none was loaded. Their final worst setup
slacks were −1.879, −0.960, and −0.547 ns. Extra post-route optimization did not
qualify the last variant. A further fixed-1R1T output-mux removal also failed
with WNS −0.716 ns; its sources and report are in
`build/latency-round4/fixed-tx-experiment/`. It was never loaded.
The retained two-cycle implementation meets timing
with WNS +0.060 ns and WHS +0.049 ns at a 6.24 ns clock constraint.

### Signal-quality evidence for the 160 MSa/s profile

The comparison retains the normal **20 MHz RX/TX analog bandwidth**, calibrated
transceiver corrections, and bit-exact FPGA arithmetic. Wider analog filters
and timing-failing FPGA images are excluded from the selected profile.
Measurements below use the actual antenna/ESPARGOS chain at 2380 MHz; they are
not a calibrated intrinsic EVM, noise-figure, or spectrum-compliance guarantee.

* Repeated 18.75 MHz occupied-band captures measured tagged SNR of
  28.02–29.28 dB at 61.44 MSa/s and 28.76–29.14 dB at 160 MSa/s. One-sided
  pilots, which separate the transfer response from mirror contamination,
  measured 30.92–31.87 dB normally and 30.97–31.82 dB fast. Response-shape
  differences were about 1 dB; normal-to-normal repeats also varied.
  With the final slow-tracking setting, a fresh normal/fast/repeated-fast
  one-sided comparison measured 31.07/31.79/31.54 dB respectively, with no
  clipping or ADC rail samples (`qec-broadband-comparison.json`).
* Matched low-band two-tone tests measured IMD3 −46.84 dBc normally and
  −48.23 dBc fast, with floors −54.69/−56.58 dBc. Band-edge results were
  −44.98/−44.19 dBc; the fast result was close to its −44.96 dBc floor and
  cannot resolve a small distortion difference.
* Source-off unaveraged captures cover RF offsets out to ±40 MHz. Fast repeat
  and normal active noise powers in the 1–10 MHz band were comparable;
  enabling the target raised the received floor by 6.17/6.38 dB respectively.
  A first fast capture had much less added noise, showing that coupling and
  feedback conditions vary. No increased fast-profile noise was resolved in
  the 10–20 or 20–35 MHz bands. These powers include receiver noise.
* No recorded FPGA clipping, ADC rail samples, or transceiver digital-filter
  overflow occurred. ADC snapshots check sampled headroom, not every sample
  throughout the capture. The MIMO validation used RX gain 35 dB and TX
  attenuation 0 dB; the single-transmitter quality tests used RX 45 dB and
  TX attenuation 10 dB.

Pluto and ESPARGOS have approximately 33 kHz of oscillator offset. It cancels
for desired echoes but displaces Pluto's IQ images by twice that offset.
Ordinary coherent captures therefore **cannot prove Pluto image rejection**.
The added raw-burst and aligned-LO tests retain those shifted images; the latter
track oscillator drift and use 64-chunk averages. Their shifted-image powers
remain dominated by the baseline measurement floor, so no intrinsic image-
rejection figure is claimed. The synthetic measurement tests verify this
estimator and its averaging-loss calculation.

More sensitive isolated tests found and corrected a receive-image difference.
With Pluto TX attenuated and all targets muted, the fast profile's default RX
tracking gave median images around −59 dBc, versus approximately −62 to −64 dBc
normally. ADI's documented slow correction-word update mode (M=4) improved the
fast results to **−63.90 dBc at low-band tones and −65.14 dBc at band-edge tones**.
Switching back to M=0 returned the low-band result to −58.79 dBc. These are
time-series medians, with noise floors around −65 to −67 dBc, rather than a
single favorable snapshot. The selected profile now enables M=4 through the
driver's `adi,qec-tracking-slow-mode-enable` setting, preserving it through LO
recalibration; normal-profile recovery restores the original setting. It changes
calibration coefficient updates, not RF sample filtering. Repeated MIMO tests
still measured 0.325 µs and the same four target delays.
See [ADI's tracking-mode description](https://github.com/analogdevicesinc/linux/blob/main/Documentation/devicetree/bindings/iio/adc/adi%2Cad9361.txt).

The isolated native TX-tone test used a filtered ESPARGOS receiver and a 1 MHz
LO offset to distinguish Pluto's image from the receiver's image and fixed spurs.
Observed TX images were −52.07 dBc fast and −53.30 dBc normally, with approximately
−63 dBc measurement floors. The native tone frequencies differ (5/5.76 MHz), so
this is not an exact same-frequency comparison. After large carrier retunes and
automatic recalibration the fast result remained −52.14 dBc. No receiver overload
occurred. This test bypasses the FPGA target bank and isolates the transmit chain.

Evidence is in `build/latency-round4/output-hold/`: `abba-fullband.json`,
`one-sided-positive.json`, `aligned64-comparison.json`, and
`noise80-comparison.json`, plus `qec-comparison.json`, `rx-sensitive-images.json`,
`tx-sensitive-images.json`, and `tx-post-retune.json`, with the underlying NPZ
captures and plots. The
tests support no resolved quality degradation within this setup's sensitivity;
they do not establish exact equivalence under every waveform or environment.

160 MSa/s is **outside AD9363's specified CMOS interface clock range**. This is a
lab profile for the connected unit, not a manufacturer-supported operating mode
or a guarantee across devices, temperatures and carriers. See the
[ADI interface limit](https://ez.analog.com/rf/wide-band-rf-transceivers/design-support/f/q-a/80716/cmos-and-lvds-data-rate).
The conditioner uses a multiplier-7 MMCM; the FPGA timing constraints include
0.75 ns setup and 0.15 ns hold uncertainty. Native startup sweeps the interface
and checks each direction for ten seconds. Recovery also checks each direction
for five seconds at the normal rate before making the UI ready.
The final FPGA passed uninterrupted **600-second RX and 600-second TX loopback
PN tests** with all four target paths active, no errors, and no clipping; FPGA
temperature stayed around 60 °C. See `160m-pn-600s-summary.json` in the result
directory. Native fault-injection and repeat-startup checks also pass with the
selected tracking mode and verify its restoration during fallback.

Use `radar-radio-fast restore` on Pluto to return to the normal muted profile.
The fast setup uses a temporary calibrated FIR clock configuration, then bypasses
the hardware FIRs and selected halfbands. The driver's FIR-enabled cache remains
1 although the hardware FIR-enable bits are 0. Do not change sample rate or FIR
settings independently in this mode: restore the normal profile first. Carrier
changes through the UI remain supported.

The sections below include the project's earlier measurements and rejected
experiments; the current implementation and new measurements take precedence.

## Start

The lab setup uses Pluto at `192.168.4.1` and ESPARGOS One at `$ESPARGOS_HOST`,
with antennas at close range. Boot selects 2380 MHz and 20 MHz analog bandwidth.
It first establishes the normal 61.44 MSa/s profile, then attempts the experimental
160 MSa/s profile. Native RX and TX integrity checks must pass before it is used.
Failure restores and checks the normal profile; all targets remain muted.

Open **http://192.168.4.1/**. The ESPARGOS-styled interface and its native control
handler run on Pluto; no laptop server, Python runtime, or SSH session is needed.
The page uses the SVG logo from `ESPARGOS/controller-firmware/main/web/logo.svg`
and the dark/green palette and typography shared by the ESPARGOS controller and
ESP-SDR interfaces. All assets are served locally, with no CDN dependencies.

Use **+ Add target**, drag to change range and Doppler, and use the
sidebar for precise total range, Doppler (Hz), and gain. Total delay is shown in
µs. Radial velocity is horizontal, using −c × Doppler / (2 × carrier), matching
the MIMO demo sign convention (positive velocity is receding). Total monostatic
range is vertical and includes hardware latency. Selecting an off-screen target
from the legend expands the window to reveal it. Four legend entries share one
row on desktop; axis labels are enlarged for readability.

The smallest range window includes the hardware minimum plus 0.1 µs of added
delay; longer windows extend to the full FPGA buffer. The delay step follows the
actual sample rate: 16.276 ns at 61.44 MSa/s, or 6.25 ns (about 0.94 m) at
160 MSa/s. Zoom does not add fractional delay resolution. Updates are automatic,
including while dragging and after scene import; each commit updates all paths
atomically. Mute all disables every echo.

The existing BusyBox HTTP server serves `/www` on port 80. At boot, `S61radar`
installs the embedded assets from `/usr/share/radar-web` and the static ARM CGI
handler from `/usr/bin/radar.cgi`. The handler validates register payloads and
uses a shared lock with `rtsctl` to serialize FPGA access. It rejects browser
writes from other origins. Device control is unauthenticated on the Pluto network.
The fast sample rate is 160 MSa/s, with 61.44 MSa/s fallback; controls read the actual hardware rate. Carrier defaults to 2380 MHz at boot; the
on-device Carrier field tunes RX and TX together from 325 to 3800 MHz, matching
the connected AD9363 driver limits. Set mutes every target before tuning and
verifies both LO readbacks. Enable targets and Apply to resume echoes. A reboot
restores the 2380 MHz default. Carrier changes do not retune ESPARGOS; configure
your radar transmitter/receiver to the same frequency separately.

Optional laptop-hosted preview or control remains available:

```sh
python3 host/server.py --demo                 # preview without hardware
python3 host/server.py --pluto 192.168.4.1     # optional SSH-based control
```

These optional modes use http://127.0.0.1:8080. Hardware mode requires `sshpass`
and the factory password, or `PLUTO_PASSWORD`. The server binds to loopback by
default. `--bind 0.0.0.0` exposes it to your LAN.

## FPGA build and volatile deployment

The existing Docker image is `ghcr.io/maia-sdr/maia-sdr-devel:latest` with Vivado
2023.2 supplied by the external `vivado2023_2` volume. The container runs as the
current user and mounts the Xilinx installation read-only.

```sh
make test       # HDL simulation, AXI/CDC tests, control validation
make fpga       # ADI IP packaging, synthesis, place/route, bitstream
make tools      # Static ARM register-control executable
./scripts/deploy.sh 192.168.4.1
```

`make fpga` downloads the ADI HDL baseline if `vendor/adi-hdl` is absent. To use
an existing local checkout without a download, set `ADI_HDL_SOURCE`. The pinned
revision is `065c8f186ef87ff049d279ed5859ee8d97d91808` from
<https://github.com/analogdevicesinc/hdl>. Upstream licenses remain in that tree.
The lab Docker image was verified as
`sha256:1d2ff3a6934152de7f83fddf996dcaf08badc10d7dfead90c462ba223b4ff2bd`.

The output is `vendor/adi-hdl/projects/pluto/pluto.runs/impl_1/system_top.bit`.
Deployment creates `build/radar.bin`, stops Maia users of the previous FPGA
register map, unbinds the radio drivers, loads FPGA RAM, rebinds the drivers, and leaves
all echoes muted. It is tailored to the connected Rev.B Pluto with Maia Linux.
It does **not** replace flash firmware. **Rebooting the Pluto restores its
installed FPGA and services.** Maia capture is unavailable while this dedicated
simulator image is loaded; do not restart Maia services against its register map.
The loader keeps `iiod` running because its FunctionFS descriptors keep the USB
gadget (including networking) connected.

On deployment, RX gain is 0 dB and TX attenuation is 60 dB. Adjust these with
normal IIO radio controls to suit the measurement. Digital target gain is
relative amplitude, not calibrated RCS or RF output power. The UI's sample-rate
setting must match the radio; rerun radio setup after changing/reloading it.

## Signal processing and limits

Each path implements approximately

`y_k[n] = gain_k * x[n - delay_k] * exp(j * phase_k[n])`

with a 32-bit phase accumulator. Paths sum into a wider accumulator and saturate
to signed 16-bit IQ, then feed the AD9361 TX input. A sticky clipping indicator
appears in the UI. AD9361 RX 12-bit samples are aligned to TX's 16-bit convention.

- Four independent targets, with shared RX/TX carrier and sample rate.
- Integer added delays from 0 to 2047 samples: **0–33.3171 µs in 16.2760 ns steps**
  at 61.44 MSa/s, or **0–12.79375 µs in 6.25 ns steps** at 160 MSa/s.
  These are added delays, not absolute RF round-trip delays.
- Signed Doppler, with **0.0372529 Hz tuning steps** at 160 MSa/s
  (0.0143051 Hz at 61.44 MSa/s). Use shifts
  within the analog passband and the radar's unambiguous Doppler interval.
- 10-bit NCO phase lookup and Q1.15 coefficients. Phase truncation/quantization
  create finite spurs; this is not a calibrated commercial channel emulator.
- Two RF logic-clock cycles of processing latency after sample capture, plus
  the ADC/DAC interfaces, filters, converter latency and physical propagation.
  Minimum absolute simulated range requires RF calibration.
- Doppler frequency changes preserve oscillator phase. An atomic configuration
  change flushes the short processing pipeline. Changing integer delay can
  introduce a phase discontinuity; fractional delay and smooth range ramps are
  not implemented. Independent range/Doppler controls do not enforce kinematics.
- All echoes emerge from one antenna. They share its apparent arrival direction;
  the simulator does not synthesize independent target angles.
- Repeated radar waveforms make delay observable modulo the waveform period.
  ESPARGOS accumulation introduces its own slow-time Doppler Nyquist limit.
- With colocated RX and TX antennas, feedback can produce unintended echoes or
  oscillation if loop gain is too high. Begin with the deployment attenuation
  and increase echo strength while checking clipping and the measured response.

The optional stock host-stream FIR filters are removed to fit the Zynq-7010.
No ARM, USB, Python or network processing is in the real-time sample path.

## Register interface

`radar_axi` is at physical address `0x43c00000`. Access with `build/rtsctl` on
Pluto (copied to `/tmp/rtsctl` by deployment). Writes go to shadow registers;
a stable mailbox plus request/acknowledge handshake applies all settings in
the RF clock domain. AXI address and data channels are accepted independently.

| Byte offset | Meaning |
| --- | --- |
| 0x00 | Signature `0x52545331` (`RTS1`) |
| 0x04 | Implementation version (current main build: `0x00010010`) |
| 0x08 | Number of targets: 4 |
| 0x0c | Maximum delay: 2047 samples |
| 0x10 | Write bit 0 to commit; bit 1 additionally restarts NCO phases |
| 0x14 | Bit 0: pending commit; bit 1: acknowledgment toggle |
| 0x18 | Sticky clipping flag, cleared on configuration/reset |
| 0x20 | Shadow target enable mask |
| 0x24 | Clock conditioner: write bit 0 to enable; read bits 0/1/2 = enabled/locked/running |
| 0x40 + 16*k | Target k delay in samples |
| 0x44 + 16*k | Target k signed phase increment (`f_D / fs * 2^32`) |
| 0x48 + 16*k | Target k unsigned Q1.15 amplitude (0–32767) |
| 0x4c + 16*k | Reserved shadow word |

`rtsctl status` returns JSON. `rtsctl mute` atomically clears the enable mask.
`rtsctl apply` reads a mask followed by four `delay increment gain` triples from
stdin, validates them and waits for acknowledgment. Do not access these physical
addresses unless the radar FPGA image is loaded.

## Verification and ESPARGOS measurement

`make test` runs a bit-exact fixed-point oracle over 15,000 clocks, exercising
four simultaneous paths, both Doppler signs, delay-memory wraparound, saturation,
sample-valid gaps, startup, mute and configuration changes. AXI tests exercise
split write channels, byte strobes, backpressure, atomic CDC configuration,
coefficient-table reload acknowledgments, immediate mute and sequenced clock switching.
The browser test uses an isolated Chromium CDP session and checks target creation,
dragging, precise edits, application, mute and mobile layout.

For the lab measurement, use the Python environment with `numpy`, `scipy`,
`matplotlib`, `pyadi-iio`, and the dependencies of the local pyespargos checkout:

```sh
python3 scripts/measure_espargos.py --scene config/four-targets.json \
  --pluto-rx-gain 35 --pluto-tx-attenuation 25 --seconds 6 \
  --output build/four-targets.npz
python3 scripts/analyze_measurement.py build/four-targets.npz
```

The recorder configures one ESPARGOS OFDM transmitter and seven receivers,
calibrates through Reference using the existing pyespargos API, records a muted
baseline and then the programmed scene. Both transmitters are muted on exit.
Raw IQ, timestamps, waveform reference and configuration are retained in NPZ;
the analysis writes a range/Doppler PNG and JSON peak estimates. The existing
`../ESPARGOS/pyespargos/demos/iq/mimo-radar` demo remains an independent receiver
reference. Use a receive rate/bandwidth compatible with the Pluto's 20 MHz path.

## Persistent firmware and live validation

The lab Pluto is flashed with the radar firmware and has successfully rebooted
from flash. `/etc/init.d/S61radar` configures the radio and leaves all targets
muted on every boot. The original kernel is retained, Maia services are disabled,
and the custom FPGA and ARM control helper are included in the image.

The original 20 MSa/s post-flash capture resolved all four simultaneous targets
(the newer low-latency image is measured below):

| Added delay | Programmed Doppler | Measured delay | Measured Doppler |
| --- | --- | --- | --- |
| 0.50 µs | −23 Hz | 3.88125 µs | −23 Hz |
| 1.50 µs | −9 Hz | 4.88125 µs | −9 Hz |
| 3.00 µs | +12 Hz | 6.38125 µs | +12 Hz |
| 4.00 µs | +27 Hz | 7.38125 µs | +27 Hz |

Delay differences agree with the settings; the common 3.38125 µs offset includes
the hardware and measurement path. This is a setup-specific observation, not an
absolute range calibration. The analysis grid is 0.125 Hz and 6.25 ns; its delay
grid uses zero padding and is finer than the waveform's resolving power.
Capture: `build/four-targets-flashed.npz` (local raw IQ),
`build/four-targets-flashed.png` (local range/Doppler plot),
`build/four-targets-flashed.json` (local peak estimates).
There were 459 coherent windows. Pluto RX gain was 35 dB, TX attenuation 25 dB,
and individual digital gains −15 dB. Hardware HTTP apply/readback and mute/readback
also passed for all four paths, without clipping during that check.

The primary web interface uses http://192.168.4.1/ and runs on Pluto itself.
The laptop server is optional. Every echo is left muted after validation. After a reboot, the
conservative boot defaults are RX 0 dB / TX attenuation 60 dB. To restore the
measured gain settings without enabling targets:

```sh
python3 - <<'PYCODE'
import adi
p = adi.Pluto('ip:192.168.4.1')
p.gain_control_mode_chan0 = 'manual'
p.rx_hardwaregain_chan0 = 35
p.tx_hardwaregain_chan0 = -25
PYCODE
```

`build/firmware/pluto.frm` is the validated persistent update image.
`python3 scripts/package_firmware.py` rebuilds it from the original device backup
and the timing-checked FPGA build. The FIT deliberately omits device-tree hashes:
Pluto U-Boot modifies those trees before booting, as it does for stock firmware.
An initial image with DTB hashes failed to boot; the original image was restored
through DFU, then the corrected image passed RAM boot before flashing and reboot.

Recovery files are `build/firmware/original.itb`, `original.frm`, and
`recovery.dfu`; `original-mtd3.bin` backs up the full original firmware partition.
Bootloader and calibration partitions were not flashed. With Pluto in DFU mode,
restore only its firmware partition using:

```sh
dfu-util -d 0456:b674 -a firmware.dfu -D build/firmware/recovery.dfu
dfu-util -d 0456:b674 -a firmware.dfu -e
```

### On-device UI verification

`tests/device_web_check.py` exercises the real Pluto web server through an
isolated Chromium CDP session on port 9223. It checks the logo and dark theme,
browser apply and FPGA readback for four targets, mute, mobile width, malformed
payload rejection, and cross-origin write rejection. Screenshots are saved as
`build/device-web-desktop.png` and `build/device-web-mobile.png`.
Rebuild native helpers with `make tools` before packaging firmware.

## MIMO performance investigation (original 20 MSa/s firmware)

Live tests used the existing MIMO demo's **two opposite-corner transmitters and
interleaved OFDM pilots**, recorded by six ESPARGOS receivers at 2380 MHz.
Raw captures and analysis are in `build/diagnostics/`; rerun
`scripts/analyze_diagnostics.py` and `scripts/replay_mimo_diagnostic.py` there
from the project root. The latter uses the existing MIMO processor with direct
path phase alignment of recorded IQ, rather than a new live GUI calibration.

Findings in this 5–10 cm antenna setup:

- **Range display is the main mismatch.** A 0.5 µs / +17 Hz target appeared at
  3.8797 µs (581.6 m) in the 20 MSa/s MIMO capture. The stock demo displays only
  0–60 m at that rate. Replaying the capture through its processor produced a
  585 m / −1.068 m/s peak with a 900 m grid (9.88 dB map peak), whereas the stock
  60 m grid produced only a 0.23 dB map peak. These map levels are normalized
  by the demo's noise estimator, not calibrated RF powers.
- **Bandwidth mismatch:** the default 80 MSa/s MIMO waveform exceeds Pluto's
  20 MSa/s sample path / 18 MHz analog bandwidth. Echo power beyond ±15 MHz was
  17.4 dB below the inner ±6 MHz region. At 80 MSa/s, per-transmitter pilot
  ambiguity is 1.6 µs, and the echo folded to about 102 m—still outside the
  demo's default 15 m display. At 20 MSa/s the ambiguity is 6.4 µs (~959 m).
- **Gain/headroom:** amplitude 0.08 and ESPARGOS RX gain 15 produced a peak
  of 31.9/512 (−24.1 dBFS). Demo settings amplitude 0.4 / RX gain 25 raised it
  to 359.3/512 (−3.1 dBFS). No FPGA clipping occurred in these captures, but
  accumulated ADC peak telemetry can hide brief overloads.
- **No evidence of sustained self-oscillation at tested gains.** With the
  ESPARGOS transmitters muted, Pluto RX gain 35 dB and TX attenuation 25 dB,
  enabling a −12 dB target changed IQ RMS by −0.14 dB; enabling a unity-gain
  target changed it by +0.42 dB. Neither clipped the FPGA. This does not rule
  out feedback with stronger analog gains, multiple coherently summed paths,
  or a different antenna arrangement.
- **Angle limitation:** at 5–10 cm the setup is in the array's near field;
  the demo's far-field angle model is not a reliable geometry model here.
  All simulated targets also share Pluto's physical transmit antenna.

Launch the existing demo with compatible defaults and a 900 m range display:

```sh
python3 scripts/mimo_radar_pluto.py
```

This local wrapper reads Pluto's current carrier, selects 20 MSa/s, amplitude
0.08 and RX gain 15, and expands the existing processor and UI range grids.
It does not edit the ESPARGOS checkout. Its `--range-max` option selects a
smaller range window; ordinary demo options pass through. Configure the Pluto
lab RF gains as described above after reboot (RX 35 dB / TX −25 dB), and enable
your desired targets. Physical range still includes the simulator hardware
latency; the wrapper does not pretend to subtract it or synthesize negative delay.

## Sub-sample distance support

The installed FPGA **still implements integer delays**: 16.7 ns / ~2.5 m steps.
Sub-sample delay is feasible by adding a fractional-delay interpolator before
Doppler rotation. A polyphase FIR or Farrow filter is appropriate. A simple
2-point linear interpolator would fit more easily, but at half a sample it
attenuates a 7 MHz baseband tone by about 6.9 dB at 20 MSa/s, so it is a poor
choice for preserving broadband MIMO pilots. A better interpolator needs a
new resource/timing-checked FPGA build and RF validation; it is not enabled by
these UI changes. It would improve delay placement, not radar range resolution,
and would not remove the remaining roughly 0.79 µs RF hardware latency.

## First latency reduction (60 MSa/s profile)

The FPGA datapath now removes 14 unnecessary interface-clock cycles by compiling
out ADI's RX data formatting, DC filtering, RX IQ correction and TX IQ correction
blocks. Runtime-disable had retained those pipeline registers. The transceiver's
own calibrated DC/IQ correction remains available. The custom bank multiplies
gain into each oscillator coefficient alongside the history read, reducing its
pipeline from five to three cycles. Coefficients remain Q1.15; the changed
rounding is covered by the bit-exact simulation oracle.

This first profile ran the actual RF interfaces at **60 MSa/s**, with RX/TX programmable
FIRs bypassed and analog bandwidth kept at 18 MHz. No simulator-latency subtraction, negative delay, or prediction is used in
the radar processor or UI; measurements use the same direct-path reference.

| RF sample rate | Original FPGA | New FPGA |
| --- | --- | --- |
| 20 MSa/s | 3.38125 µs | 2.58125 µs |
| 40 MSa/s | 1.72500 µs | 1.32500 µs |
| 60 MSa/s | 1.16875 µs | 0.90000 µs |

These are over-the-air zero-programmed-delay measurements using the same 17 Hz
probe and direct-path reference. The new operating point reduces measured latency
by **73.4%** from the original configuration. The 6.25 ns peak-search grid is
interpolated, not an absolute accuracy specification. The 16-cycle FPGA reduction
matches the measured 0.8 µs difference at 20 MSa/s and 0.4 µs at 40 MSa/s.

The complete image passed RAM boot, flash readback, and a persistent reboot.
`build/latency/flashed-zero.npz` independently reproduced **0.900 µs** from the
boot profile without changing its sample clock or FIR state. Browser apply,
mute, carrier tuning, and target auto-reveal passed after reboot.

All captures are in `build/latency/`. Four simultaneous targets were also measured
at 60 MSa/s: programmed 0.5/1.5/3/4 µs delays appeared near 1.4/2.4/3.906/4.9 µs,
with −23/−9/+12/+27 Hz Dopplers. The largest discrepancy from a common 0.90 µs
offset is one peak-search grid bin. Final timing at the design's 61.46 MHz RX
clock constraint passed with WNS +0.977 ns and WHS +0.018 ns. DSP usage fell from
60/80 to 32/80. The 12,000-clock datapath oracle and AXI/CDC tests passed.

The buffer remains 2048 samples: maximum added delay is now 34.1167 µs instead of
102.35 µs. Delay spacing improves from about 7.5 m to 2.5 m; this is higher hardware
sampling, not fractional interpolation. The ESPARGOS radar may still run at
20 MSa/s because the analog echo bandwidth remains 18 MHz. The base delay now
corresponds to about 135 m, so the original narrow MIMO display still needs a
wide enough range window to observe it.

For controlled comparisons, `measure_espargos.py --pluto-sample-rate` explicitly
sets the hardware clock with FIRs bypassed. Avoid the `pyadi-iio` convenience
`sample_rate` setter for this profile: it loads/enables a long FIR automatically.
An intermediate measurement with that FIR enabled is retained separately as
`old-fpga-40m.npz`; it is excluded from the FIR-bypassed comparison table.

The pre-change working firmware and bitstream are retained in
`build/latency/original/`. Host scratch files use
`$RTS_SCRATCH_DIR/`; the Docker wrapper uses the
same directory (override with `RTS_SCRATCH_DIR`). Pluto's own `/tmp` remains its
volatile runtime filesystem, separate from host scratch storage.

## Further interface latency reduction (previous three-cycle firmware)

The current build removes five more RF-clock register stages from the ADI
interface: the RX common-clock transfer, the unused internal TDD output stage,
two TX DMA-source registers, and the TX common-clock transfer. The patch is
opt-in (`RADAR_LOW_LATENCY`) and assumes Pluto's `clk` and `l_clk` are the same
net, continuous 1R1T operation, and FPGA IQ correction disabled. The normal
PN/DDS/loopback sources remain available for digital interface calibration.
The three-cycle, four-target processing bank is unchanged.

The boot profile now uses 61.44 MSa/s with 20 MHz analog bandwidth and both
programmable FIRs disabled. Actual RF measurements, relative to the independently
captured direct path, are:

| FPGA interface | Sample rate | Analog bandwidth | Zero-added-delay RF latency |
| --- | --- | --- | --- |
| Previous | 60 MSa/s | 18 MHz | 0.9000 µs |
| Previous | 60 MSa/s | 20 MHz | 0.8875 µs |
| Previous | 61.44 MSa/s | 20 MHz | 0.86875 µs |
| New | 60 MSa/s | 18 MHz | 0.8125 µs |
| New | 61.44 MSa/s | 20 MHz | 0.7875 µs |

This is a further 12.5% reduction, to approximately 118 m equivalent monostatic
range. These values come from a 6.25 ns interpolated peak grid, not a claim of
6.25 ns absolute accuracy. No latency subtraction, prediction, or negative delay
is applied. A true 0.1 µs minimum has not been achieved.

All four independent targets passed RF validation. At programmed delays
0.5/1.5/3/4 µs and Dopplers −23/−9/+12/+27 Hz, peaks occurred at
1.29375/2.2875/3.7875/4.7875 µs, respectively. Integer sample quantization at
61.44 MSa/s is included when checking these results; no FPGA clipping was observed.

The source patch is `patches/adi-radar-low-latency.patch`, applied idempotently
by `scripts/prepare_hdl.py`. Timing passed with WNS +0.785 ns and WHS +0.010 ns.
The existing 12,000-clock fixed-point oracle and AXI/CDC tests pass, as does a
new 1,000-sample interface simulation covering IQ order, pipeline latency, and
retained calibration/zero sources.

Raw captures and reports are in `build/latency-round2/`. Analysis searches within
±0.5 Hz of each known Doppler tag: the old ±2 Hz search could select unrelated
moving clutter at zero delay. The full delay interval remains unconstrained.
A synthetic interfering-clutter regression verifies this selection.

An experimental lower-oversampling clock profile with a short impulse FIR was
slower (1.05 µs). Bypassing that FIR with raw registers measured 0.8375 µs on
the previous interface, but left driver FIR state inconsistent with hardware;
that experimental profile is not installed. Requesting 56 MHz analog bandwidth
was clamped to 20 MHz by the AD9363 driver. Neither experiment is relied on by
the production configuration.

The previous complete firmware and bitstream are preserved under
`build/latency-round2/known-good/`.

The 20 MSa/s two-transmitter MIMO pilots also produced a correctly tagged
17 Hz echo at 0.79375 µs (one analysis bin from the single-TX result), with
estimated ESPARGOS ADC peak 32.4/512 and no FPGA clipping.

The complete firmware was flashed with full readback verification and rebooted.
The independent post-reboot capture (`flashed-zero.npz`) measured 0.78750 µs
without changing the boot clock/FIR profile. The device-served HTML matches
the corrected source after reboot. Saved target/carrier/gain settings were
restored with all targets muted. Firmware SHA-256 is recorded in
`build/latency-round2/firmware.sha256`.


## Two-cycle target bank and internal-filter experiments

The target bank now produces its output two clocks after input capture, instead
of three. Gain-scaled NCO coefficients are captured alongside the history read;
the next stage multiplies IQ, and the last stage sums and saturates. Explicit
`DONT_TOUCH` on the gain mailbox destination registers keeps the bundled CDC
endpoints from being absorbed into DSP input registers. The first implementation
exposed that constraint issue and was not deployed; the corrected implementation
passes timing (WNS +1.534 ns, WHS +0.022 ns). The exact fixed-point oracle verifies
6,390 outputs across 12,000 clocks, with AXI/CDC and interface regressions passing.

All measurements below retain the actual 61.44 MSa/s interface rate and compare
against an independently captured direct RF path. They do not subtract simulator
latency or exploit the radar waveform's repetition to synthesize an early echo.
The peak-search grid is 6.25 ns; that is not absolute measurement accuracy.

| Configuration | Zero-added-delay RF latency |
| --- | --- |
| Previous three-cycle bank, normal filters | 0.78750 µs |
| Two-cycle bank, normal filters | 0.77500 µs |
| Three-cycle bank, alternate halfbands, requested 56 MHz analog bandwidth | 0.71875 µs |
| Two-cycle bank, same experimental filters | 0.70625 µs |
| Two-cycle bank, same experimental filters, MIMO pilots | 0.70000 µs |
| Direct FPGA RX-to-TX bypass, normal filters | 0.72500 µs |
| Direct FPGA RX-to-TX bypass, experimental filters | 0.65000 µs |

The direct-bypass measurements use diagnostic TX source 10 and tag the echo
using a TX LO offset. That source bypasses target delay, gain and Doppler entirely;
it is not a usable four-target simulator mode. Normal operation remains source 2.
This establishes an observed radio/interface floor for these tested profiles,
not a universal lower bound for the transceiver. At that stage, sub-0.5 µs had not yet been achieved.

`scripts/experimental_filter_profile.py` performs reversible transceiver filter
experiments. The best tested profile is `--profile rx-no-hb1 --bandwidth 56000000`:
it uses explicit converter/halfband clocks and requested analog bandwidth through
the driver's FIR configuration, then bypasses the temporary unity FIR in hardware.
This leaves the driver's FIR-enable cache at 1 while the actual FIR bits are 0.
Use `--profile stock` or reboot to restore a consistent normal profile. The wider
analog passband has not been fully characterized, and this profile is not the
firmware default. Bypassing every halfband and disabling RX quadrature/DC tracking
did not improve the best measured latency. The RX port's programmable delay was
already zero. Raw results and profile/register snapshots are in
`build/latency-round3/`; the previous firmware is in its `known-good/` directory.

An isolated five-cycle candidate also passes internal FPGA timing at an 8.13 ns
RX clock constraint (WNS +0.647 ns, WHS +0.009 ns). Its source, bitstream and report
are preserved in `build/latency-round3/fast-interface/`, with the complete isolated
build in `$RTS_SCRATCH_DIR/fast-interface`.
At the end of that round it had not been hardware tested; the next section
records the subsequent tests. The corresponding 122.88 MHz CMOS
interface would exceed the AD9363's specified [61.44 MHz CMOS clock limit](https://ez.analog.com/rf/wide-band-rf-transceivers/design-support/f/q-a/80716/cmos-and-lvds-data-rate). Internal FPGA timing
does not validate the external interface, which still needs clock/data integrity
and RF tests. This candidate is not part of the installed firmware.

The two-cycle firmware with the normal 20 MHz/FIR-bypassed radio profile was
flashed, readback-verified, and rebooted. A fresh zero-delay capture measured
0.77500 µs. Four simultaneous targets programmed at 0.5/1.5/3/4 µs and
−23/−9/+12/+27 Hz appeared at 1.28125/2.27500/3.76875/4.77500 µs with matching
Dopplers and no FPGA clipping. These results include integer delay quantization.
The hosted UI matches the source; the saved 2385 MHz carrier, gains, and four
muted targets were restored. Firmware hash: `build/latency-round3/firmware.sha256`.


## Initial 122.88 MSa/s experiment: low latency but rejected quality

**Subsequent quality checks rejected this initial 122.88 MSa/s configuration.**
Every saved RF capture from the five-cycle design at that rate latched the FPGA
clipping flag, including a single target at a gain that cannot mathematically
clip. Longer TX-loopback checks also reported errors. The latency peaks below
are observations, not an accepted operating point. A six-cycle version with
additional timing margin and unused DDS logic disabled also failed the tiny-gain
check at 122.88 MSa/s. Investigation continues; the installed firmware is intact.

With explicit authorization for the CMOS interface overclock, the five-cycle
FPGA was loaded into volatile RAM. The normal converter clocks remain unchanged:
RX ADC 491.52 MHz and TX DAC 245.76 MHz. Bypassing RX HB1 and TX HB2 changes the
interface to an actual 122.88 MSa/s, as reported by the clock chain. This exceeds
the AD9363's specified CMOS clock rate; a passing FPGA timing report is not a
substitute for external-interface validation.

| 122.88 MSa/s configuration | Measured zero-added-delay RF latency |
| --- | --- |
| 20 MHz analog bandwidth, single ESPARGOS transmitter | 0.41875 µs |
| 20 MHz analog bandwidth, established MIMO pilots | 0.41250 µs |
| Experimental wider-filter profile | 0.38750 µs |

These are actual receive-to-transmit measurements. The FPGA remains a general
streaming delay/Doppler bank; there is no waveform prediction, repetition-based
range synthesis, or fixed-latency subtraction. The 6.25 ns analysis grid does
not imply that absolute measurement accuracy. The wider profile additionally has the documented FIR-cache mismatch and an
uncharacterized wider passband.

Four simultaneous targets at programmed 0.5/1.5/3/4 µs with −31/−17/+17/+31 Hz
Dopplers were resolved at 0.91875/1.91875/3.42500/4.42500 µs with matching Dopplers.
The initial −9/+12 Hz tags were obscured by direct-path clutter; the repeat used
separated tags and eight seconds of integration. ESPARGOS control requests also
intermittently timed out during setup. `measure_espargos.py --http-close` requests
fresh control connections and allowed subsequent captures to complete, without
changing the RF processing or modifying ESPARGOS firmware.

The initial fast bank source is `experiments/fast-interface/target_bank_5cycle.sv`;
`target_bank.sv` in the same directory is the later six-cycle experiment; the isolated
Vivado project remains under the scratch path documented above. It uses the same
`radar_axi.sv`, CDC constraints and interface patch as the normal design, but
an 8.13 ns RX clock constraint and five-cycle oracle expectation. Its archived
bitstream and timing report are in `build/latency-round3/fast-interface/`.
`scripts/deploy_fast_experiment.sh` now refuses deployment because the initial
image failed sustained integrity checks. The archived captures remain diagnostic
evidence, not a deployable release. Reboot restores the installed two-cycle
61.44 MSa/s image.

`scripts/experimental_fast_clock.py --fast-fpga-loaded` applies the raw halfband
bypasses; it must only be used with the prepared fast FPGA. `--wide` selects the
experimental wider-filter profile. Returning from 122.88 MSa/s first restores
the bypassed /2 stage before invoking the driver's rate validator, which rejects
122.88 MSa/s through its ordinary API. `experimental_filter_profile.py --profile
stock` can restore that normal clock profile, or a reboot restores the complete
installed FPGA/radio configuration.

The interface test is `scripts/check_radio_pn.py`. ADC FPGA register access needs
the driver's 0x80000000 PCORE address bit; omitting it silently reads zeros and
is not a valid PN test. RX PRBS uses PN9; TX-to-RX digital loopback uses the FPGA's
custom PN source/checker. Source registers are restored and TX stays attenuated.
Raw captures, profiles, timing scans and checker results are retained in
`build/latency-round4/`, including failed diagnostic attempts.

## Conditioned-clock investigation (ongoing)

A six-cycle variant inserts a selectable MMCM into the FPGA RF clock path. At
122.88 MSa/s and normal 20 MHz bandwidth, it passed 60 seconds each of RX PN and
TX-loopback PN with all four target paths active and bounded gains: no checker
errors or FPGA clipping. Live MIMO measured 0.44375 µs at zero programmed delay.
Four targets at 0.5/1.5/3/4 µs and −31/−17/+17/+31 Hz appeared at
0.9375/1.9375/3.44375/4.44375 µs without clipping. A 30-second broadband capture
also reported no FPGA clipping. These captures are in
`build/latency-round4/clock-cleaner/`.

The initial two-tone comparison measured approximately −37.4 dBc third-order
products at both 61.44 and 122.88 MSa/s, near the measurement floor. Image levels
remain setup-dependent; this is not yet proof of identical RF quality over the
whole passband or under all operating conditions. No conditioned-clock firmware
has been flashed.

The first clock mux design can stall when disabling the MMCM because it removes
the outgoing clock before BUFGCTRL completes the switch. Re-enabling the MMCM
recovers it. The next revision holds the MMCM running for 256 AXI clock cycles
after selecting the raw clock, before asserting reset. Its control simulation
passes; implementation and hardware tests are pending.

`experiments/fast-interface/target_bank_precomputed.sv` is a four-cycle sample
pipeline experiment. Four FPGA-generated coefficient tables preserve the exact
existing gain/NCO quantization while removing gain multiplication from the
per-sample path. A target commit temporarily mutes output while 1024 entries
are generated (1027 clocks before accepting new output samples). The independent
fixed-point oracle passes with phase continuity, configuration changes, sample
gaps, delay wrap and saturation. The first three-cycle version failed timing (RAM read to multiplier), so it
was rejected before deployment. The current four-cycle revision adds DSP input
registers; implementation and RF qualification are pending.

The sequenced clock-control revision (`0x10002`) passed live switching tests.
On the same bitstream, repeated raw/conditioned/raw/conditioned trials produced
impossible tiny-gain clipping only with the raw clock. The conditioned clock
passed a further ten seconds of PN stress in each direction. Evidence is in
`build/latency-round4/clock-switch/`. The `clock_conditioner.py` helper refuses
to disable the older unsafe revision and checks the MMCM input-rate range.

A repeated rated-rate broadband capture varied by 3.7–4.0 dB across the strongest
receivers' individual-bin amplitude ratios (5th–95th percentile), comparable to
the 3.0–4.2 dB differences between rated and fast captures. Thus these antenna
measurements do not resolve small passband-shape changes. The overall tagged
SNR was 17.1 dB rated versus 19.0 dB fast. Do not interpret this comparison as a
calibrated EVM or flatness specification.

### Further FPGA and interface experiments

The current laboratory candidates use gain-scaled coefficient tables and
prefetched historical samples. Prefetch uses only samples already received and
known oscillator phases; it never predicts or repeats the incoming waveform.
Double-buffered tables let the old scene run while a new scene is prepared.
The FPGA acknowledges a configuration only after the atomic table handoff; mute
is immediate. Independent arithmetic tests cover 15,000 clocks with valid gaps,
configuration replacement, signed Doppler, delay wrap, phase continuity, and
saturation. A separately pipelined sticky clipping monitor does not add RF delay.

Measured zero-added-delay MIMO latencies at 2380 MHz, normal 20 MHz bandwidth:

| FPGA | Actual interface rate | RF delay | Integrity evidence |
| --- | --- | --- | --- |
| Precomputed four-cycle (`0x10004`) | 122.88 MSa/s | 0.41875 µs | 10 s per-direction PN stress, no RF clipping |
| Prefetch three-cycle (`0x10005`) | 128 MSa/s | 0.40000 µs | 10 s per-direction PN stress, no RF clipping |
| Prefetch three-cycle (`0x10005`) | 136 MSa/s | 0.37500 µs | 10 s per-direction PN stress, no RF clipping |
| Buffered prefetch (`0x10006`) | 144 MSa/s | 0.36250 µs | 60 s per-direction PN stress, four live targets |

The four 144 MSa/s targets at programmed 0.5/1.5/3/4 µs appeared at
0.8625/1.8625/3.3625/4.3625 µs with matching −31/−17/+17/+31 Hz Dopplers.
The 149.76 MSa/s multiplier-8 MMCM setup was rejected: a Q-channel TX PN data
error latched after 6.53 seconds of loaded testing. Complete halfband bypass at
144 MSa/s also failed its TX PN check and was rejected before RF capture.
Keeping only RX HB3 and bypassing all TX halfbands gave 0.36875 µs, slightly
slower than the standard fast profile.

A requested 56 MHz analog bandwidth reached 0.32500 µs at 144 MSa/s; diagnostic
source 10 bypassing the target bank measured 0.29375 µs. This wider passband
changes out-of-band rejection and exceeds the AD9363 bandwidth specification,
so it is not automatically a quality-preserving replacement for 20 MHz operation.
The diagnostic bypass supplies no target bank and is not a simulator mode.

At stronger excitation, the four-cycle 122.88 MSa/s candidate and a rated-rate
reference both measured about 27 dB tagged broadband SNR. A 60-second fast
two-tone capture measured −44.64 dBc third-order products (nearby floor −56.33
dBc); the 12-second reference measured −45.33 dBc (floor −48.08 dBc). These
remain comparisons through the antenna/ESPARGOS measurement chain, not intrinsic
transceiver specifications. Band-edge and 18.75 MHz occupied-band tests are now
available through `measure_espargos.py --tone-bins 79 101` and
`--occupied-bins 120`. The distortion analyzer has independent low/edge-tone
regressions with known spur levels and strong static clutter.

`host/radio_pn.c` builds a standalone on-device checker. It detected deliberately
bad RX timing and passed after restoring the qualified setting, verifying that
its good results are not vacuous zero-register reads. All experimental changes
remain volatile; the installed firmware is still the normal two-cycle image.

The completed 30-second 18.75 MHz occupied-band comparison at 144 MSa/s with
**20 MHz analog filtering** measured 28.96 dB tagged SNR versus 28.63 dB at
61.44 MSa/s, with no FPGA clipping. Segment gain spans were 0.39 and 0.38 dB.
The strongest receiver's relative amplitude-shape span was 1.30 dB and residual
phase RMS 0.052 rad after removing constant gain and linear delay; multipath and
measurement noise remain in that comparison. Band-edge tones (6.172 and
7.891 MHz) gave IMD3 −45.64 dBc (floor −48.04 dBc), versus −39.54 dBc (floor
−53.31 dBc) at the rated rate. The fast result is close to its measurement floor;
it supports no observed degradation, not a precise intrinsic distortion claim.
Files: `build/latency-round4/buffered-three-cycle/normal-*-comparison.json`.

The next candidate (`0x1000b`) keeps three sample cycles by adding target pairs
in the rotation stage and doing the final pair sum/saturation in the output
stage. A local gain register feeds each coefficient-preparation DSP, preserving
the explicit CDC capture flops while removing their multiplier timing path.
Its independent oracle includes zero, one-LSB and near-full-scale gains.
It meets a 6.24 ns clock constraint with 0.750 ns setup / 0.150 ns hold
uncertainty: WNS +0.117 ns, WHS +0.005 ns. The MMCM uses multiplier/divider 6.
Timing qualification alone does not qualify the overclocked radio interface;
live PN and RF results are required separately. The image and source manifest
are in `build/latency-round4/pairs-gainpipe/`.

The 144 MSa/s `0x10006` image subsequently passed uninterrupted **600-second RX
and 600-second TX loopback PN tests**, with all four bounded-gain target paths
active and no clipping. See `144m-pn-600s-summary.json` in its result directory.

Further interface qualification rejected 160 MSa/s on the multiplier-6 image:
its RX calibration had no stable window. A longer FPGA input-delay sweep found
two briefly clean points, but neither survived a 0.5-second recheck, so neither
was retained. At 150 MSa/s, multiplier-6 and multiplier-8 images initially failed
TX PN checks with the default transceiver drive. Stronger documented CMOS drive
(register 0x03B = 0x44) is now under test. The FPGA's default TX slew was also
confirmed as SLOW, DRIVE=12; a separate FAST-slew image has been timing-qualified.
These electrical-interface changes require fresh RF quality checks.

On-device startup/recovery tests cover repeat setup, explicit restore, deliberate
checker failure, and restarting normal radio setup from the fast profile. An
actual failed TX startup check also correctly restored 61.44 MSa/s, 20 MHz,
FIR bypass, stopped clock conditioner, and muted targets. The helper now also
saves/restores digital drive settings; this addition awaits its live regression.

### Raw input headroom checks

The retained Maia device tree does not expose an IIO ADC scan buffer. The lab-only
`make capture-tool` builds `radio-capture`, which uses the FPGA receive DMA to
capture 65,536 IQ samples by default into the existing unused Maia spectrometer
reservation. Optional counts of 262,144 or 1,048,576 improve spectral resolution;
pass the same count with `--adc-samples` to the measurement script.
It verifies the device-tree reservation, disabled owner, DMA identity and inactive
state before use, then disables the DMA and restores its configuration. It adds
no stages to the radar sample path and is not required by the firmware or UI.
Copy `build/radio-capture` to Pluto's `/tmp/radio-capture` and pass
`--capture-pluto-dma` to `measure_espargos.py` to save a snapshot after the RF
measurement. This is a sampled headroom check, not continuous overload monitoring.

The measurement also records the transceiver's latched digital overflow status
before and after each capture. The field includes BBPLL lock in bit 7; clear
bits 0–6 indicate no recorded digital-filter overflow. This is distinct from
ADC input headroom. Register definitions: [ADI UG-672, pp. 25 and 50](https://www.analog.com/media/cn/technical-documentation/user-guides/AD9364_Register_Map_Reference_Manual_UG-672.pdf).
