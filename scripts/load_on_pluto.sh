#!/bin/sh
# Load a compatible Pluto image into RAM. All changes are volatile.
set -eu
[ -f /tmp/radar.bin ] && [ -x /tmp/rtsctl ]
rm -f /tmp/radar-loaded /tmp/radar-failed
# Stop known applications that own the old register map before reconfiguration.
# DICHASUS starts this process directly; its init script has no stop action.
if pidof maia-reftx >/dev/null; then killall maia-reftx; fi
# Its script also launches the transmitter on "stop", which blocks reboot.
# Move it out of the init directory in RAM; reboot restores the installed copy.
if [ -f /etc/init.d/S60dichasus ]; then
 mv /etc/init.d/S60dichasus /tmp/radar-saved-S60dichasus
fi
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
if ! sh /tmp/radio_setup.sh || ! sh /tmp/radio_fast_setup.sh; then
 touch /tmp/radar-failed
 echo '160 MSa/s startup failed; targets muted; simulator unavailable'
 exit 1
fi
touch /tmp/radar-loaded
printf 'Volatile radar image loaded. Reboot Pluto to restore the installed firmware.\n'
