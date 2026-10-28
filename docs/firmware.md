# Installing and recovering the firmware

## Compatibility

The firmware has been tested on a **Rev.B Pluto running Maia Linux**. The
packager retains that image's kernel, root filesystem, USB/network setup and
three revision-specific device trees. It stops the Maia services that use the FPGA and installs
the radar bitstream, control programs, startup script and web interface.

You need a compatible base image at `build/firmware/original.itb`; the build
reuses its Linux kernel and root filesystem. A second Rev.B device running a DICHASUS image has also been tested by loading
the FPGA and UI into RAM; this does not qualify that image as a packaging base.
Other kernels, factory firmware and other Pluto revisions still need testing. The driver must provide the
AD9361 IIO/debug attributes used by `radio_fast_setup.sh`, including
`adi,qec-tracking-slow-mode-enable`, and the retained reserved-memory layout.

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
ssh root@192.168.4.1 'cat /proc/mtd; cat /proc/device-tree/model'
ssh root@192.168.4.1 'dd if=/dev/mtdblock3 bs=65536' > build/firmware/original-mtd3.bin
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
make fpga tools
make firmware
sha256sum build/firmware/pluto.frm
```

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
./scripts/deploy.sh 192.168.4.1
```

This loads FPGA RAM and configures the radio without changing flash. It stops
Maia services, temporarily rebinds radio drivers, preserves the USB gadget and
leaves targets muted. Reboot restores the installed image. This command copies
the FPGA and radio tools; use the firmware image to install the web interface.
Stop any other application that owns the radio before deployment. In particular,
DICHASUS may run `maia-reftx` from its startup script; that script does not support
a `stop` argument. The loader handles Maia services but does not stop arbitrary
third-party applications for you.

## Writing the firmware to flash

The updater writes the `qspi-linux` partition. It checks the Rev.B model,
partition name and checksum before muting the targets and writing the image.
It then reads back the image to verify the write and updates U-Boot's `fit_size`.
The matching `rtsctl` must already be available at `/tmp/rtsctl` (from a running
radar image or volatile deployment).

```sh
scp -O build/firmware/pluto.frm root@192.168.4.1:/tmp/radar.frm
scp -O scripts/flash_on_pluto.sh root@192.168.4.1:/tmp/flash_on_pluto.sh
ssh root@192.168.4.1 'sh /tmp/flash_on_pluto.sh'
# Continue only after successful flash readback verification:
ssh root@192.168.4.1 reboot
```

Startup initially selects 2380 MHz, 20 MHz bandwidth, RX 0 dB and TX −60 dB.
It checks the fast profile for ten seconds in each direction; fallback checks
the normal profile for five seconds per direction. Once those checks finish,
the web controls become available. If setup fails, read `/tmp/radar-startup.log`
or run `/tmp/rtsctl status` on the Pluto. Scenes are not restored on reboot.

The web controls have no authentication; use the device USB/private lab network.
Some base images generate a new SSH host key on each reboot.
Verify device identity over its direct USB connection before replacing a stored
key; do not disable SSH host verification globally.

## DFU recovery

For the tested bootloader, create a DFU-suffixed copy of the **original FIT**:

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
