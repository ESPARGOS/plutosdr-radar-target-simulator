# PlutoSDR radar target simulator

Four independently delayed and Doppler-shifted echoes, generated entirely in the
PlutoSDR FPGA. A web interface runs on the Pluto itself: place targets, drag them
in range/velocity, and adjust the carrier, RX gain and TX gain. No host computer
processes or streams the radar samples.

![Pluto-hosted target editor](docs/assets/web-interface.png)

## What it does

- Four targets with independent delay, signed Doppler, amplitude and On/Off state.
- Continuous, logarithmic plot zoom; selected slider panels respond to the wheel.
- Automatic hardware updates, including during dragging; scene import/export.
- Total monostatic range in metres and radial velocity in m/s, with delay and
  Doppler shown in the sidebar. The unavailable minimum range is shaded.
- Local ESPARGOS styling, fonts and favicon; no CDN or laptop web server needed.
- One firmware image containing the FPGA, Linux system, controls and web UI.

The current FPGA is version `0x00010010`. The qualified lab configuration uses
**160 MSa/s digital processing with 20 MHz analog RF bandwidth** and measured
**0.325 µs RF latency**, equivalent to a minimum monostatic range of about **48.7 m**.
160 MSa/s does **not** mean a 160 MHz reflected RF passband.

| Property | Current lab profile |
| --- | --- |
| Targets | 4 |
| Added delay | 0–2047 samples; 0–12.79375 µs |
| Delay step | 6.25 ns, approximately 0.94 m in monostatic range |
| Doppler tuning step | approximately 0.03725 Hz |
| Analog RX/TX bandwidth | 20 MHz |
| Carrier control | 325–3800 MHz, subject to the installed AD9363 driver |
| Minimum measured RF latency | 0.325 µs, setup-specific |

**The 160 MSa/s profile exceeds the AD9363's specified CMOS interface clock range.**
It was tested on one Rev.B Pluto with Maia firmware. Startup checks RX and TX
integrity and falls back to a checked 61.44 MSa/s profile on failure. This is an
experimental instrument, not a calibrated target simulator or a qualification
of every Pluto. See [validation and limitations](docs/validation.md).

## Use it

On a Pluto with the radar firmware installed, open **http://192.168.4.1/**.

1. Set the carrier to match the radar. Changing carrier mutes the targets.
2. Adjust RX/TX gains for the setup; boot defaults are RX 0 dB and TX −60 dB.
3. Use **+ Add target**. New targets start On. Drag a point or edit its sidebar.
4. Select the Range and/or Velocity panel to choose which axes the wheel zooms.
   **Fit targets** reveals the entire scene. Clicking empty plot space does nothing.
5. Use the joined **On | Off** controls or **Mute all** to disable echoes.

Edits apply automatically. Reboot starts with muted/empty hardware state and
restores boot radio defaults; export scenes you want to keep. RX gain edits select
manual gain control. Radio gains are distinct from each target's digital gain.

For a hardware-free preview (Python 3.10+; standard library only):

```sh
make web
# Open http://127.0.0.1:8080/
```

## FPGA datapath

![Four parallel FPGA target paths](docs/assets/fpga-datapath.svg)

## Build and install

Start with [the build guide](docs/build.md). FPGA builds use pinned ADI HDL and a
pinned Maia development container, plus an externally supplied Vivado/Vitis 2023.2
installation. AMD tools are not included in the container or repository.

```sh
make test       # current HDL/control regressions in the build container
make fpga       # synthesize and route the FPGA
make tools      # cross-compile native ARM controls
make firmware   # package using your compatible base firmware
```

The resulting all-in-one update is `build/firmware/pluto.frm`. The packager
**requires a compatible base FIT image**, retaining its kernel and root filesystem;
it does not build those components from source. Follow the
[firmware, backup and recovery guide](docs/firmware.md) before flashing.
Firmware binaries, device backups, vendor checkouts and raw RF captures are
excluded from Git. The source tree is not a stock-Pluto universal firmware recipe.

## Documentation

- [Build environment and commands](docs/build.md)
- [Firmware packaging, deployment and recovery](docs/firmware.md)
- [Architecture, signal processing and HTTP API](docs/architecture.md)
- [FPGA register interface](docs/registers.md)
- [Validation results and hardware limitations](docs/validation.md)
- [Tests and ESPARGOS measurements](docs/testing.md)
- [Contribution guide](CONTRIBUTING.md)
- [Third-party components and attribution](THIRD_PARTY.md)
- [Archived development notebook](docs/development-history.md)

## Source layout

| Directory | Purpose |
| --- | --- |
| `rtl/` | Current four-target bank, AXI control and CDC constraints |
| `patches/` | Changes applied to the pinned ADI HDL baseline |
| `host/` | Native Pluto controls, boot service and optional preview server |
| `web/` | Device-hosted UI, bundled font and ESPARGOS assets |
| `scripts/` | Build/deploy tools, RF measurement and diagnostic utilities |
| `tests/` | HDL, Python, browser and hardware regressions |
| `config/` | Example scenes and an illustrative lab configuration |
| `experiments/` | Historical alternatives; not used by the normal build |
| `docs/` | Current guides and selected validation records |

## License

Original project code, documentation and the included ESPARGOS assets are
licensed under **GNU GPL version 3** (`GPL-3.0-only`); see [LICENSE](LICENSE).
Bundled font data, upstream HDL and firmware components retain their own terms;
see [third-party notices](THIRD_PARTY.md).
