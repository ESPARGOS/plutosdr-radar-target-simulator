# Third-party components and attribution

Original radar-target-simulator code and documentation are GPL-3.0-only; see
[LICENSE](LICENSE). The owner of the ESPARGOS assets has also authorized their
inclusion under GPLv3 for this project. This grant does not replace third-party
licenses or grant rights in AMD tools or unrelated upstream firmware.

| Component | Origin | Terms / treatment |
| --- | --- | --- |
| ESPARGOS logo and favicon | `ESPARGOS/controller-firmware`, `main/web/` | Included under GPL-3.0-only with the owner's authorization |
| UI visual reference | [ESPARGOS/esp-web-sdr](https://github.com/ESPARGOS/esp-web-sdr), controller UI | ESPARGOS dark/green styling; project UI code is GPL-3.0-only |
| Carlito font embedded in `web/fonts.css` | Carlito Project Authors / Google Fonts, via ESPARGOS web SDR | SIL Open Font License 1.1; full copyright and license retained at the top of `fonts.css` |
| ADI HDL | [analogdevicesinc/hdl](https://github.com/analogdevicesinc/hdl), revision `065c8f186ef87ff049d279ed5859ee8d97d91808` | Fetched, not vendored in Git. Per-module notices and upstream LICENSE files govern ADI code; patches retain upstream notices; the ADIBSD text is also in [LICENSES/ADIBSD.txt](LICENSES/ADIBSD.txt) |
| Maia development container | [maia-sdr/maia-sdr](https://github.com/maia-sdr/maia-sdr) | External build dependency; component licenses remain upstream |
| Vivado/Vitis 2023.2 | AMD | User-supplied proprietary toolchain; not redistributed |
| Linux, BusyBox, libraries and device trees in base firmware | User-supplied compatible Pluto FIT image | Their individual licenses apply; not supplied as source or binary in this repository |
| pyespargos | [ESPARGOS/pyespargos](https://github.com/ESPARGOS/pyespargos) | Optional external measurement dependency; its own license applies |

The native tools statically link the toolchain's C runtime. A distributed
firmware release must include applicable notices and the corresponding source
and other materials required by the licenses of its components. A GitHub source
checkout alone is not the corresponding source for an externally supplied Linux
root filesystem. Record the exact base image and toolchain when preparing releases.

The SVG FPGA diagram is original project documentation under GPL-3.0-only.
No third-party web scripts or online font requests are needed by the device UI.
