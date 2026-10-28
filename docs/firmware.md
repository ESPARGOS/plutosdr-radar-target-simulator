# Firmware, deployment and recovery

## Compatibility

The tested device is a **Rev.B Pluto running a Maia-derived Linux image**. The
packager retains that image's kernel, root filesystem, USB/network setup and
three revision-specific device trees. It disables Maia FPGA users and installs
the radar bitstream, tools, boot service and web files.

This repository does not provide a Linux/Buildroot build or a redistributable
base image. It requires `build/firmware/original.itb` from a compatible system.
A factory firmware image, another revision or another kernel is not qualified
by the existing measurements. In particular, the driver must provide the
AD9361 IIO/debug attributes used by `radio_fast_setup.sh`, including
`adi,qec-tracking-slow-mode-enable`, and the retained reserved-memory layout.

The expected FIT image order is rev-a DTB, rev-b DTB, rev-c DTB, FPGA, kernel,
rootfs; check `dumpimage -l` before packaging. Keep the base firmware's source
version and license records with any distributed binary release. Do not assume
the project license covers Linux, BusyBox, ADI/AMD IP or the base image.

## Back up first

Keep your device's original firmware and recovery method before installing.
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
These checks do not prove kernel/hardware compatibility.

## Build an all-in-one image

```sh
make fpga tools
make firmware
sha256sum build/firmware/pluto.frm
```

`make firmware` runs `scripts/package_firmware.py`, which requires passing final
FPGA timing. Outputs are `pluto.frm`, `pluto.frm.sha256`, `radar.itb`, `radar.bit`
and the intermediate rootfs/DTB files under `build/firmware/`.
The `.frm` is the complete application firmware update, not a bootloader image.
Device-tree hashes are deliberately omitted: Pluto U-Boot patches the DTBs
before boot, as in the base firmware. Other FIT components have hashes.

## Volatile deployment

```sh
make tools
./scripts/deploy.sh 192.168.4.1
```

This loads FPGA RAM and configures the radio without changing flash. It stops
Maia services, temporarily rebinds radio drivers, preserves the USB gadget and
leaves targets muted. Reboot restores the installed image. This path installs
FPGA/radio helpers, not the persistent web interface.

## Persistent installation

The tested SSH updater writes only the `qspi-linux` partition. On the supported
Rev.B layout it checks model, partition name and image checksum, mutes targets,
flashes, verifies the entire written image, and updates U-Boot's `fit_size`.
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
the normal profile for five seconds per direction. The UI becomes ready after
setup finishes. On-device diagnostics are `/tmp/radar-startup.log` and
`/tmp/rtsctl status`. Boot does not restore a browser scene.

The web controls have no authentication; use the device USB/private lab network.
Firmware based on a volatile SSH key setup may generate a new host key on reboot.
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
