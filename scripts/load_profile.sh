#!/bin/sh
# Change the FPGA while the radio is muted, then let the AD9363 driver recalibrate.
set -eu
case "${1:-}" in
 standard) expected=0x00020003 ;;
 overclocked) expected=0x00020002 ;;
 *) echo 'Expected standard or overclocked FPGA profile' >&2; exit 2 ;;
esac
[ "$(devmem 0x43c00004)" != "$expected" ] || exit 0
image="radar-$1.bin"
[ -r "/lib/firmware/$image" ] || { echo "Missing FPGA image: $image" >&2; exit 1; }
/tmp/rtsctl mute
rm -f /tmp/radar-loaded
if [ -f /tmp/radar-fast-recovery ]; then
 RADAR_DEFER_TUNING=1 sh /usr/bin/radar-radio-fast restore
fi
for d in /sys/bus/iio/devices/iio:device*; do
 if [ "$(cat "$d/name")" = ad9361-phy ]; then
  echo -89.75 > "$d/out_voltage0_hardwaregain"
 fi
done
for pair in 'cf_axi_dds 79024000.cf-ad9361-dds-core-lpc' 'cf_axi_adc 79020000.cf-ad9361-lpc'; do
 set -- $pair
 if [ -L "/sys/bus/platform/devices/$2/driver" ]; then
  echo "$2" > "/sys/bus/platform/drivers/$1/unbind"
 fi
done
if [ -L /sys/bus/spi/devices/spi0.0/driver ]; then
 echo spi0.0 > /sys/bus/spi/drivers/ad9361/unbind
fi
echo 0 > /sys/class/fpga_manager/fpga0/flags
echo "$image" > /sys/class/fpga_manager/fpga0/firmware
[ "$(cat /sys/class/fpga_manager/fpga0/state)" = operating ]
[ "$(devmem 0x43c00004)" = "$expected" ]
echo spi0.0 > /sys/bus/spi/drivers/ad9361/bind
for pair in 'cf_axi_dds 79024000.cf-ad9361-dds-core-lpc' 'cf_axi_adc 79020000.cf-ad9361-lpc'; do
 set -- $pair
 if [ ! -L "/sys/bus/platform/devices/$2/driver" ]; then
  echo "$2" > "/sys/bus/platform/drivers/$1/bind"
 fi
done
