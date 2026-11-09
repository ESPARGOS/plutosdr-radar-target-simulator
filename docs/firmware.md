# Installing and recovering the firmware

## Compatibility

The simulator runs on **Rev.B and Rev.C Pluto** hardware with the required AD9361 driver
controls. It does not need Maia SDR installed. The packager preserves the supplied
Pluto image's kernel, root filesystem, USB/network setup and device trees, then
adds both radar FPGA images, tools, startup script and web interface.

Known radio startup services from DICHASUS and Maia-derived images are removed
when present, so they cannot compete for the FPGA. Maia device-tree nodes are
disabled only if they exist. Those compatibility steps are not runtime
dependencies. The development container's `maia-sdr` name identifies its publisher.

The driver must provide the IIO/debug attributes used by `radio_fast_setup.sh`,
including `adi,qec-tracking-slow-mode-enable`.
Compatibility with other Pluto revisions and driver versions is not guaranteed.

The expected FIT image order is rev-a DTB, rev-b DTB, rev-c DTB, FPGA, kernel,
rootfs; check `dumpimage -l` before packaging. Keep the base firmware's source
version and license records with any distributed binary release. Do not assume
the project license covers Linux, BusyBox, ADI/AMD IP or the base image.

## Backing up the existing firmware

Save the original firmware before installing, so you can recover it if needed.
The following reads only `qspi-linux`; verify its partition name is `mtd3` on
**your** device before using these example commands:

```sh
mkdir -p build/firmware
ssh root@192.168.2.1 'cat /proc/mtd; cat /proc/device-tree/model'
ssh root@192.168.2.1 'dd if=/dev/mtdblock3 bs=65536' > build/firmware/original-mtd3.bin
python3 scripts/import_base_firmware.py build/firmware/original-mtd3.bin
dumpimage -l build/firmware/original.itb
```

Use your configured SSH credentials. The stock Pluto password is `analog`;
never put a personal password or private key in the repository. A saved compatible
`.frm` can also be passed to `import_base_firmware.py`. It checks the FIT header
and FRM checksum when present, and refuses to replace a different existing base.
The importer checks the file format, but cannot tell whether its kernel supports
the required radio controls.

## Build an all-in-one image

```sh
make fpga
make firmware
# To use a different device backup without replacing the default base:
make firmware FIRMWARE_ARGS="--base build/firmware/second-original.itb --output build/firmware/second-pluto"
sha256sum build/firmware/pluto.frm
```

`make fpga` builds separate standard and overclocked images. Both are included
in the firmware so the radio-panel mode selector can load the matching datapath.

`make firmware` runs `scripts/package_firmware.py`, which requires passing final
FPGA provenance and timing, plus matching native tools. It also records all
package inputs in `firmware-manifest.json`. Outputs are `pluto.frm`, `pluto.frm.sha256`, `radar.itb`, `radar.bit`
and the intermediate rootfs/DTB files under `build/firmware/`.
The `.frm` is the complete application firmware update, not a bootloader image.
Device-tree hashes are deliberately omitted: Pluto U-Boot patches the DTBs
before boot, as in the base firmware. Other FIT components have hashes.

## Trying a bitstream without flashing

```sh
make tools
./scripts/deploy.sh 192.168.2.1
```

This loads FPGA RAM and configures the radio without changing flash. It stops
known radio applications, temporarily rebinds radio drivers, preserves the USB gadget and
leaves targets muted. The matching control tools and web interface are copied
into RAM as well. Reboot restores the installed image and its web interface.
The loader handles DICHASUS's `maia-reftx` process and Maia's HTTP service when
present. It moves DICHASUS's init script out of the init directory in RAM because
that script also starts its transmitter when called with `stop`, blocking reboot.
Reboot restores the original installed files. Stop any other application that
owns the radio before deployment.

## Writing the firmware to flash

The updater writes the `qspi-linux` partition. It checks for a Rev.B/Rev.C model,
partition name and checksum before muting the targets and writing the image.
It then reads back the image to verify the write and updates U-Boot's `fit_size`.
The matching `rtsctl` must already be available at `/tmp/rtsctl` (from a running
radar image or volatile deployment).

```sh
scp -O build/firmware/pluto.frm root@192.168.2.1:/tmp/radar.frm
scp -O scripts/flash_on_pluto.sh root@192.168.2.1:/tmp/flash_on_pluto.sh
ssh root@192.168.2.1 'sh /tmp/flash_on_pluto.sh'
# Continue only after successful flash readback verification:
ssh root@192.168.2.1 reboot
```

Startup selects 2385 MHz and 20 MHz bandwidth. RX stays at 0 dB and TX at
−60 dB during calibration. After the checks pass, it selects the operating
defaults of RX 25 dB and TX −35 dB, with targets still muted.
At the overclocked rate, calibration first searches the transceiver's RX data
delay together with the FPGA input delays, keeping DATA_CLK fixed. This avoids
rejecting a usable combination just because the initial FPGA delay was poor.
If that search fails, it scans the full RX clock/data grid. TX calibration scans
all 256 clock/data pairs. Candidate settings pass a one-second PN check, and
the joint RX/TX input-delay window is checked while updating all four targets.
A final five-second TX check and RX recheck qualify the selected setting.
Calibration normally takes about 35 seconds in overclocked mode. Marginal
candidates and fallback can take longer. The controls become available after these checks.
The web status shows the current stage and elapsed startup time. The FPGA is
already loaded when the radio checks run.
If the 160 MSa/s check fails, startup restores and validates the normal 61.44 MSa/s
profile before enabling the controls. The UI identifies fallback mode
and uses its 1.35 µs reference latency (202.4 m minimum range). If either
recovery or standard-profile validation fails, targets stay muted and the API
returns an error. The radio-panel mode selector saves the requested mode in
`/mnt/jffs2/radar-mode`. Selecting Standard skips the 160 MSa/s attempt. A mode
change mutes transmission, clears targets and runs
the checks again. Bandwidth, carrier frequency and gains are preserved. A reboot retries
the selected mode. Read `/tmp/radar-startup.log` or run `/tmp/rtsctl status`
on the Pluto to diagnose startup failures. Target movement runs in the FPGA. Scenes are not restored on reboot.

The web controls have no authentication; use the device USB/private lab network.
Some base images generate a new SSH host key on each reboot.
Verify device identity over its direct USB connection before replacing a stored
key; do not disable SSH host verification globally.

## DFU recovery

Create a DFU-suffixed recovery image from your **original FIT**:

```sh
cp build/firmware/original.itb build/firmware/recovery.dfu
dfu-suffix -v 0456 -p b674 -a build/firmware/recovery.dfu
```

Put Pluto into DFU mode using its hardware recovery procedure. Check
`dfu-util -l` for USB `0456:b674` and alternate `firmware.dfu`, then restore only
that alternate:

```sh
dfu-util -d 0456:b674 -a firmware.dfu -D build/firmware/recovery.dfu
dfu-util -d 0456:b674 -a firmware.dfu -e
```

Do not substitute bootloader or calibration alternates. Keep a copy of the
original `fit_size` (`fw_printenv fit_size`) with the backup; restoring a different
FIT may also require restoring that value from a working recovery shell.
