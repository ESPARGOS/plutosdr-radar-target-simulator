#!/bin/sh
# Intended for the lab Pluto running Maia firmware. All changes are volatile.
set -eu
[ -f /tmp/radar.bin ] && [ -x /tmp/rtsctl ]
rm -f /tmp/radar-loaded
# Stop users of the old register map before reconfiguration.
if [ -f /etc/init.d/S60maia-httpd ]; then /etc/init.d/S60maia-httpd stop || true; fi
# Keep iiod running: its FunctionFS file descriptors hold the whole USB gadget up.
for d in /sys/bus/iio/devices/iio:device*; do
 if [ "$(cat "$d/name")" = ad9361-phy ]; then echo -89.75 > "$d/out_voltage0_hardwaregain"; fi
done
if [ -f /tmp/radar-fast-recovery ]; then
 sh /tmp/radio_fast_setup.sh restore
fi
if [ -L /sys/bus/platform/devices/7c400000.maia-sdr/driver ]; then
 echo 7c400000.maia-sdr > /sys/bus/platform/drivers/uio_pdrv_genirq/unbind
fi
for pair in 'cf_axi_dds 79024000.cf-ad9361-dds-core-lpc' 'cf_axi_adc 79020000.cf-ad9361-lpc'; do
 set -- $pair
 if [ -L "/sys/bus/platform/devices/$2/driver" ]; then echo "$2" > "/sys/bus/platform/drivers/$1/unbind"; fi
done
if [ -L /sys/bus/spi/devices/spi0.0/driver ]; then echo spi0.0 > /sys/bus/spi/drivers/ad9361/unbind; fi
cp /tmp/radar.bin /lib/firmware/radar.bin
echo 0 > /sys/class/fpga_manager/fpga0/flags
echo radar.bin > /sys/class/fpga_manager/fpga0/firmware
cat /sys/class/fpga_manager/fpga0/state
echo spi0.0 > /sys/bus/spi/drivers/ad9361/bind
for pair in 'cf_axi_dds 79024000.cf-ad9361-dds-core-lpc' 'cf_axi_adc 79020000.cf-ad9361-lpc'; do
 set -- $pair
 if [ ! -L "/sys/bus/platform/devices/$2/driver" ]; then echo "$2" > "/sys/bus/platform/drivers/$1/bind"; fi
done
sh /tmp/radio_setup.sh
fast_status=0
sh /tmp/radio_fast_setup.sh || fast_status=$?
case "$fast_status" in
 0) ;;
 1) echo 'Fast profile failed validation; using verified normal profile' ;;
 *) echo 'Radio recovery failed'; exit 1 ;;
esac
touch /tmp/radar-loaded
printf 'Volatile radar image loaded. Reboot Pluto to restore the installed firmware.\n'
