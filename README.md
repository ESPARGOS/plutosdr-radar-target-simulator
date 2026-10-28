# PlutoSDR radar target simulator

This project turns a PlutoSDR into a radar target simulator. It receives a signal,
adds up to four echoes with different delays and Doppler shifts, and transmits
them back. The signal processing runs in the FPGA; a web interface on the Pluto
lets you move targets around and adjust their strength.

![The target editor running on Pluto](docs/assets/web-interface.png)

You can drag targets in range and velocity, enter exact settings in the sidebar,
or save a scene to use again later. Changes take effect as you drag. The interface
also controls the carrier frequency and RX/TX gains.

## Performance

With the current FPGA (`0x00010010`), we measured **0.325 µs of RF latency**,
which corresponds to a minimum simulated monostatic range of about **48.7 m**.
The plot includes this delay and shades the region below the minimum range.

The FPGA processes samples at **160 MSa/s**, while the radio's analog bandwidth
is **20 MHz**. At a carrier of 2385 MHz, that gives a nominal passband of roughly
2375–2395 MHz, with gradual roll-off at the edges.

| Setting | Range or resolution |
| --- | --- |
| Targets | Up to 4 |
| Added delay | 0–2047 samples, or 0–12.79375 µs |
| Delay step | 6.25 ns, about 0.94 m in monostatic range |
| Doppler step | About 0.03725 Hz |
| RX/TX analog bandwidth | 20 MHz |
| Carrier frequency | 325–3800 MHz with the installed AD9363 driver |

**160 MSa/s exceeds the AD9363's specified CMOS interface clock range.** We tested
this configuration on a Rev.B Pluto running Maia firmware. At startup, the radio
checks both data directions and falls back to 61.44 MSa/s if either check fails.
The latency and signal-quality measurements, including their limits, are in
[the measurement notes](docs/validation.md).

## Using the simulator

With the radar firmware installed, open **http://192.168.4.1/**.

1. Set the carrier to match your radar. Changing it mutes all targets.
2. Set the RX and TX gains. The startup defaults are RX 0 dB and TX −60 dB.
3. Click **+ Add target**, then drag the point or edit its settings. New targets
   are enabled automatically.
4. Click the Range or Velocity panel to include that axis in mouse-wheel zoom.
   You can select both. **Fit targets** brings all targets into view.
5. Use **On | Off** for an individual target, or **Mute all** to silence them all.

There is no Apply button: edits take effect immediately. Use Export to keep a
scene across reboots, since the simulator starts with no active targets. Setting
RX gain switches the receiver to manual gain control. Each target also has a
digital gain, separate from the radio's RX and TX gains.

To try the interface without hardware, you only need Python 3.10 or later:

```sh
make web
# Open http://127.0.0.1:8080/
```

## How it works

Each path delays the incoming samples, applies a Doppler shift and scales their
amplitude. The four echoes are then added together and sent to the transmitter.

![The four FPGA target paths](docs/assets/fpga-datapath.svg)

The [architecture guide](docs/architecture.md) describes the arithmetic,
configuration interface and scene format.

## Building the firmware

You will need Vivado/Vitis 2023.2 and Docker. The build uses a fixed ADI HDL
revision and Maia development image; you supply the AMD tool installation.
See [the build guide](docs/build.md) for setup.

```sh
make test       # run the HDL and control tests
make fpga       # build the FPGA bitstream
make tools      # build the ARM control programs
make firmware   # assemble the firmware image
```

The result is `build/firmware/pluto.frm`, containing the FPGA, Linux system and
web interface. Packaging uses the kernel and root filesystem from a compatible
Pluto/Maia FIT image that you provide. Follow the
[installation and recovery guide](docs/firmware.md) to back up your device,
prepare that image and flash the result. Other base firmware versions and Pluto
revisions still need testing.

Build outputs, firmware backups and raw captures stay in `build/` and are excluded
from Git.

## Documentation

- [Build setup](docs/build.md)
- [Installation, backups and recovery](docs/firmware.md)
- [Signal processing and HTTP API](docs/architecture.md)
- [FPGA registers](docs/registers.md)
- [Measurements and limitations](docs/validation.md)
- [Running tests and ESPARGOS measurements](docs/testing.md)
- [Contributing](CONTRIBUTING.md)
- [Third-party licenses](THIRD_PARTY.md)

## Source layout

| Directory | Contents |
| --- | --- |
| `rtl/` | Target processing, AXI registers and clock-domain constraints |
| `patches/` | Changes to the ADI HDL |
| `host/` | Pluto control programs, startup script and preview server |
| `web/` | Web interface and its assets |
| `scripts/` | Build tools, deployment scripts and measurement utilities |
| `tests/` | Simulation, analysis and browser tests |
| `config/` | Example scenes and lab settings |
| `docs/` | Guides, diagrams and measurement results |

## License

The project code, documentation and included ESPARGOS assets are licensed under
**GNU GPL version 3** (`GPL-3.0-only`); see [LICENSE](LICENSE). Fonts, upstream HDL
and firmware components keep their own licenses, listed in
[THIRD_PARTY.md](THIRD_PARTY.md).
