# Building

Run these commands from the repository root. You will need Linux, Python 3.10+,
GNU Make, Git and Docker, with permission to run Docker as your user.
For packaging, also install U-Boot tools (`mkimage`, `dumpimage`) and device-tree
compiler tools (`fdtget`, `fdtput`). Arch package names include `docker`, `git`, `make`,
`python`, `uboot-tools` and `dtc`; equivalent Debian packages are `docker.io`,
`git`, `make`, `python3`, `u-boot-tools` and `device-tree-compiler`.

## Toolchain

The build-only container is published by Maia SDR; Maia software is not required
on the Pluto. The container is pinned to:

```text
ghcr.io/maia-sdr/maia-sdr-devel@sha256:a5cb1b566f18db4072cc2148cc46052241d9fd1eeae07ea1984aacd2552f9e85
```

The build expects a Vivado/Vitis **2023.2** installation with these files:

- `Vivado/2023.2/settings64.sh`
- `Vitis/2023.2/gnu/aarch32/lin/gcc-arm-linux-gnueabi/bin/arm-linux-gnueabihf-gcc`

The default Docker volume name is `vivado2023_2`. Alternatively, mount an existing
installation directory:

```sh
export RTS_XILINX_VOLUME=/path/to/Xilinx
export RTS_SCRATCH_DIR="$PWD/build/scratch"
./scripts/container.sh vivado -version
```

`RTS_XILINX_VOLUME` accepts a named Docker volume or absolute host directory.
It is mounted read-only at `/opt/Xilinx`; project sources are mounted at `/work`.
Set `RTS_BUILD_IMAGE` if you want to try a different container image. Temporary
files go in `build/scratch` by default.
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
from an existing checkout instead of downloading it. The sources are extracted into
`vendor/adi-hdl` and reused on later runs. If you change the ADI revision, start
with a fresh vendor directory.

Outputs:

- `vendor/adi-hdl/projects/pluto/pluto.runs/impl_1/system_top.bit`
- `vendor/adi-hdl/projects/pluto/timing_impl.log`
- `build/rtsctl`, `build/radar.cgi`, `build/radio-pn`
- `build/fpga-manifest.json`, `build/tools-manifest.json`

`make fpga` records the exact input files, toolchain, bitstream and passing timing
report in `build/fpga-manifest.json`. It reuses an existing build only when all
those hashes still match. Otherwise it performs a clean implementation; an old
bitstream cannot be assigned a new manifest after the fact.

`python3 scripts/check_build.py` verifies that record before packaging or
deployment. Changing an RTL file, integration patch, prepared ADI source,
bitstream or timing report makes the check fail. `make tools` similarly records
the native sources, compiler and output binaries. `make firmware` rebuilds the
tools, verifies both manifests, and writes `build/firmware/firmware-manifest.json`
with the base image, startup scripts, web assets and final firmware hashes.

A passing build still needs radio tests, particularly after clock or interface
changes. Packaging uses the base image described in [firmware.md](firmware.md);
flashing is a separate step.

For tests without Vivado/Docker, install Icarus Verilog, prepare the vendor tree,
and run `make test-local`. Analysis tests additionally use
`python3 -m pip install -r requirements-test.txt`, then `make test-analysis`.
The optional `make capture-tool` builds the lab-only native ADC snapshot utility.

The hashes of the tested firmware are in
[the build manifest](validation/firmware-manifest.json). Rebuilding can produce
different hashes because the tools include timestamps in some outputs.
