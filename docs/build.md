# Building

Run commands from the repository root. Linux, Python 3.10+, GNU Make, Git and
Docker are needed for the container build. Your user must have Docker access.
For packaging, also install U-Boot tools (`mkimage`, `dumpimage`) and device-tree
compiler tools (`fdtput`). Arch package names include `docker`, `git`, `make`,
`python`, `uboot-tools` and `dtc`; equivalent Debian packages are `docker.io`,
`git`, `make`, `python3`, `u-boot-tools` and `device-tree-compiler`.

## Toolchain

The container is pinned to:

```text
ghcr.io/maia-sdr/maia-sdr-devel@sha256:a5cb1b566f18db4072cc2148cc46052241d9fd1eeae07ea1984aacd2552f9e85
```

Supply a licensed Vivado/Vitis **2023.2** installation containing
`Vivado/2023.2/settings64.sh` and
`Vitis/2023.2/gnu/aarch32/lin/gcc-arm-linux-gnueabi/bin/arm-linux-gnueabihf-gcc`.
The default Docker volume name is `vivado2023_2`. Alternatively, mount an existing
installation directory:

```sh
export RTS_XILINX_VOLUME=/path/to/Xilinx
export RTS_SCRATCH_DIR="$PWD/build/scratch"
./scripts/container.sh vivado -version
```

`RTS_XILINX_VOLUME` accepts a named Docker volume or absolute host directory.
It is mounted read-only at `/opt/Xilinx`; project sources are mounted at `/work`.
`RTS_BUILD_IMAGE` overrides the pinned container only when intentionally testing
another environment. Scratch files default to `build/scratch`, not host `/tmp`.
The container runs with the caller's UID/GID and host networking.

## Sources and outputs

```sh
make prepare
make test
make fpga
make tools
```

`prepare` fetches ADI HDL revision
`065c8f186ef87ff049d279ed5859ee8d97d91808`, generates the NCO ROM and applies the
integration patches. Set `ADI_HDL_SOURCE=/path/to/hdl` to archive that revision
from an existing checkout instead of downloading it. `vendor/adi-hdl` is an
extracted working tree, not a submodule. An existing vendor tree is reused;
use a fresh checkout/build tree when changing the pinned revision.

Outputs:

- `vendor/adi-hdl/projects/pluto/pluto.runs/impl_1/system_top.bit`
- `vendor/adi-hdl/projects/pluto/timing_impl.log`
- `build/rtsctl`, `build/radar.cgi`, `build/radio-pn`

`python3 scripts/check_build.py` rejects a build whose final timing report does
not pass. Timing success alone is not hardware/RF qualification. `make firmware`
packages the tools and bitstream using the base image described in
[firmware.md](firmware.md). This task does not flash a device.

For tests without Vivado/Docker, install Icarus Verilog, prepare the vendor tree,
and run `make test-local`. Analysis tests additionally use
`python3 -m pip install -r requirements-test.txt`, then `make test-analysis`.
The optional `make capture-tool` builds the lab-only native ADC snapshot utility.

The working reference build is recorded in
[the validation manifest](validation/firmware-manifest.json). Source rebuilds may
contain timestamps and are not promised to be byte-identical firmware images.
