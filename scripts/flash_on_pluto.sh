#!/bin/sh
# Flash only qspi-linux, matching the factory update format. Bootloader and NVM stay intact.
set -eu
image=/tmp/radar.frm
[ -s "$image" ]
grep -q 'qspi-linux' /proc/mtd
grep -q 'Rev.B' /proc/device-tree/model
expected=$(tail -c 33 "$image")
actual=$(head -c -33 "$image" | md5sum | cut -d ' ' -f 1)
[ "$actual" = "$expected" ] || { echo 'Firmware checksum failed'; exit 1; }
grep -q 'ITB PlutoSDR (ADALM-PLUTO)' "$image"
size=$(wc -c < "$image")
[ "$size" -lt 31457280 ]
fit_size=$(printf '%X' "$((size-33))")
/tmp/rtsctl mute
flashcp -v "$image" /dev/mtd3
expected_full=$(md5sum "$image" | cut -d ' ' -f 1)
actual_full=$(head -c "$size" /dev/mtdblock3 | md5sum | cut -d ' ' -f 1)
[ "$actual_full" = "$expected_full" ] || { echo 'Flash readback mismatch'; exit 1; }
fw_setenv fit_size "$fit_size"
sync
printf 'Firmware flashed and readback verified. '
fw_printenv fit_size
