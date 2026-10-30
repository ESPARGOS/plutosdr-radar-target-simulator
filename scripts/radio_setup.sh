#!/bin/sh
# Run on Pluto AFTER loading the FPGA and rebinding its drivers.
set -eu
phy=/sys/bus/iio/devices/iio:device0
for d in /sys/bus/iio/devices/iio:device*; do
 [ "$(cat "$d/name")" != ad9361-phy ] || phy="$d"
done
# Keep TX attenuated throughout clock and interface calibration.
echo -60 > "$phy/out_voltage0_hardwaregain"
# A service restart can begin in the fast profile. Restore its calibrated clock
# chain before asking the driver's FIR validator to select the normal profile.
if [ -f /tmp/radar-fast-recovery ]; then
 restore=/usr/bin/radar-radio-fast
 [ -x "$restore" ] || restore=/tmp/radio_fast_setup.sh
 sh "$restore" restore
fi
version=$(devmem 0x43c00004)
case "$version" in
 0x00010000) ;; # Original normal-rate image has no clock-control register.
 *)
  [ "$(devmem 0x43c00024)" = 0x00000000 ] || {
   echo 'Restore the active experimental profile before normal radio setup' >&2
   exit 1
  }
  ;;
esac
echo 2385000000 > "$phy/out_altvoltage0_RX_LO_frequency"
echo 2385000000 > "$phy/out_altvoltage1_TX_LO_frequency"
# Keep the programmable FIRs bypassed; their group delay dominates latency.
echo 0 > "$phy/in_out_voltage_filter_fir_en"
echo 61440000 > "$phy/in_voltage_sampling_frequency"
echo 20000000 > "$phy/in_voltage_rf_bandwidth"
echo 20000000 > "$phy/out_voltage_rf_bandwidth"
echo manual > "$phy/in_voltage0_gain_control_mode"
echo 0 > "$phy/in_voltage0_hardwaregain"
echo fdd > "$phy/ensm_mode"
# DMA source selection exposes the custom datapath on TX IQ, without a TX DMA stream.
devmem 0x79024418 32 2
devmem 0x79024458 32 2
# Keep both RX channels enabled and sign-extended, even without an IIO capture.
devmem 0x79020400 32 0x51
devmem 0x79020440 32 0x51
/tmp/rtsctl mute
printf 'Radio configured: 2385 MHz, 61.44 MSa/s, 20 MHz BW, RX 0 dB, TX -60 dB\n'
