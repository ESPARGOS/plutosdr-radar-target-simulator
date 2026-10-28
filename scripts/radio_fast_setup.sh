#!/bin/sh
# On-Pluto, after radio_setup.sh establishes the normal muted 61.44 MHz profile.
# Experimental CMOS clock profile: hardware FIRs bypassed; driver FIR cache is 1.
# No host processing. On failure restore a verified normal, muted radio profile.
set -eu
wanted=${1:-160000000}
case "$wanted" in restore|128000000|136000000|144000000|150000000|160000000) ;; *) echo 'Unsupported fast rate' >&2; exit 2;; esac
phy=
for d in /sys/bus/iio/devices/iio:device*; do
 if [ "$(cat "$d/name")" = ad9361-phy ]; then phy=$d; break; fi
done
[ -n "$phy" ]
debug=/sys/kernel/debug/iio/${phy##*/}
qec_mode=$debug/adi,qec-tracking-slow-mode-enable
checker=/usr/bin/radio-pn
[ -x "$checker" ] || checker=/tmp/radio-pn
version=$(devmem 0x43c00004)
case "$version" in
 0x00010006) [ "$wanted" = restore ] || [ "$wanted" -le 144000000 ];;
 0x00010009|0x0001000B|0x0001000D|0x00010010) [ "$wanted" = restore ] || [ "$wanted" -le 160000000 ];;
 0x0001000C) [ "$wanted" = restore ] || [ "$wanted" -le 150000000 ];;
 *) echo "Unqualified fast FPGA revision: $version" >&2; exit 2;;
esac
rx_saved=;tx_saved=;io_saved=;qec_saved=;complete=0
recovery=/tmp/radar-fast-recovery
if [ -f "$recovery" ]; then
 # Older volatile recovery files have three fields and did not change QEC.
 read -r rx_saved tx_saved io_saved qec_saved < "$recovery"
fi
spi_write() { printf '0x%x 0x%x\n' "$1" "$2" > "$debug/direct_reg_access"; }
spi_read() { printf '0x%x\n' "$1" > "$debug/direct_reg_access"; cat "$debug/direct_reg_access"; }
restore_normal() {
 # Cleanup is best-effort until final readback; TX remains attenuated throughout.
 set +e
 echo -60 > "$phy/out_voltage0_hardwaregain"
 devmem 0x43c00024 32 0
 sleep 1
 if [ -n "$qec_saved" ]; then
  echo "$qec_saved" > "$qec_mode"
  tracking=$(cat "$phy/in_voltage_quadrature_tracking_en")
  echo "$tracking" > "$phy/in_voltage_quadrature_tracking_en"
 fi
 if [ -n "$rx_saved" ] && [ -n "$tx_saved" ]; then
  echo alert > "$phy/ensm_mode"
  spi_write 3 "$rx_saved";spi_write 2 "$tx_saved"
  [ -z "$io_saved" ] || spi_write 0x3b "$io_saved"
  echo fdd > "$phy/ensm_mode"
 fi
 # Refresh parent-to-child clock caches after the raw register restoration.
 cat "$phy/rx_path_rates" "$phy/tx_path_rates"
 echo 0 > "$phy/in_out_voltage_filter_fir_en"
 echo 61440000 > "$phy/in_voltage_sampling_frequency"
 echo 20000000 > "$phy/in_voltage_rf_bandwidth"
 echo 20000000 > "$phy/out_voltage_rf_bandwidth"
 /tmp/rtsctl mute
 actual=$(cat "$phy/in_voltage_sampling_frequency")
 tx_actual=$(cat "$phy/out_voltage_sampling_frequency")
 difference=$((actual-61440000));tx_difference=$((tx_actual-61440000))
 rx_check=$(spi_read 3);tx_check=$(spi_read 2)
 [ "$difference" -ge -100 ] && [ "$difference" -le 100 ] &&
  [ "$tx_difference" -ge -100 ] && [ "$tx_difference" -le 100 ] &&
  [ "$(cat "$phy/in_voltage_rf_bandwidth")" = 20000000 ] &&
  [ "$(cat "$phy/out_voltage_rf_bandwidth")" = 20000000 ] &&
  [ "$(cat "$phy/in_out_voltage_filter_fir_en")" = 0 ] &&
  [ $((rx_check & 3)) -eq 0 ] && [ $((tx_check & 3)) -eq 0 ] &&
  [ "$(devmem 0x43c00024)" = 0x00000000 ] || return 1
 if [ -n "$io_saved" ]; then
  io_check=$(spi_read 0x3b);[ "$((io_check))" -eq "$((io_saved))" ] || return 1
 fi
 if [ -n "$qec_saved" ]; then
  [ "$(cat "$qec_mode")" = "$qec_saved" ] || return 1
  qec_check=$(spi_read 0x16f)
  [ "$(((qec_check >> 5) & 7))" -eq "$((qec_saved * 4))" ] || return 1
 fi
 # Correct clock readbacks alone do not prove that the restored port is clean.
 "$checker" 5 || return 1
 rm -f "$recovery"
}
if [ "$wanted" = restore ]; then restore_normal; exit $?; fi
# Repeated startup is allowed only after restoring the saved calibrated chain.
if [ -f "$recovery" ]; then restore_normal || exit 2; set -e; fi
actual=$(cat "$phy/in_voltage_sampling_frequency")
[ "$actual" -le 61440100 ] || { echo 'Restore the current fast profile first' >&2; exit 2; }
finish() {
 result=$?
 trap - 0
 if [ "$complete" -eq 0 ]; then
  echo "Fast radio setup failed (status $result); restoring normal profile" >&2
  if restore_normal; then
   echo 'Normal 61.44 MSa/s profile restored; targets muted' >&2
   exit 1
  else
   echo 'Normal profile restoration failed; TX remains attenuated' >&2
   exit 2
  fi
 fi
}
trap finish 0
trap 'exit 1' 1 2 15
/tmp/rtsctl mute
echo -60 > "$phy/out_voltage0_hardwaregain"
devmem 0x43c00024 32 0
sleep 1
base=$((wanted/4))
io_saved=$(spi_read 0x3b)
qec_saved=$(cat "$qec_mode")
case "$qec_saved" in 0|1) ;; *) echo 'Invalid QEC driver mode' >&2; exit 1;; esac
[ "$(cat "$phy/in_voltage_quadrature_tracking_en")" = 1 ]
# ADI's slow correction-word update mode improves narrowband RX image rejection
# at this high sample rate. It adds no filter or register to the RF sample path.
# Change the driver's setting too, so subsequent LO calibrations retain it.
echo 1 > "$qec_mode"
echo 1 > "$phy/in_voltage_quadrature_tracking_en"
{
 printf 'TX 3 GAIN 0 INT 2\nRX 3 GAIN 0 DEC 2\n'
 printf 'RTX %d %d %d %d %d %d\n' "$((8*wanted))" "$((2*wanted))" "$wanted" "$((wanted/2))" "$((wanted/2))" "$base"
 printf 'RRX %d %d %d %d %d %d\n' "$((8*wanted))" "$((4*wanted))" "$((2*wanted))" "$wanted" "$((wanted/2))" "$base"
 printf 'BWRX 20000000\nBWTX 20000000\n32767,32767\n'
 n=0;while [ "$n" -lt 15 ]; do printf '0,0\n';n=$((n+1));done
} > /tmp/radar-fast.ftr
cat /tmp/radar-fast.ftr > "$phy/filter_fir_config"
echo 1 > "$phy/in_out_voltage_filter_fir_en"
rx_saved=$(spi_read 3);tx_saved=$(spi_read 2)
printf '%s %s %s %s\n' "$rx_saved" "$tx_saved" "$io_saved" "$qec_saved" > "$recovery"
echo alert > "$phy/ensm_mode"
spi_write 3 "$((rx_saved & ~7))"
spi_write 2 "$((tx_saved & ~11))"
# UG-671: stronger CMOS DATA_CLK/data-port drive, fastest rise/fall setting.
# Preserve CLK_OUT drive, which is independent of the data interface.
spi_write 0x3b "$(((io_saved & 128) | 68))"
echo fdd > "$phy/ensm_mode"
cat "$phy/rx_path_rates" "$phy/tx_path_rates"
actual=$(cat "$phy/in_voltage_sampling_frequency");difference=$((actual-wanted))
[ "$difference" -ge -100 ] && [ "$difference" -le 100 ]
tx_actual=$(cat "$phy/out_voltage_sampling_frequency");difference=$((tx_actual-wanted))
[ "$difference" -ge -100 ] && [ "$difference" -le 100 ]
[ "$(cat "$phy/in_voltage_rf_bandwidth")" = 20000000 ]
[ "$(cat "$phy/out_voltage_rf_bandwidth")" = 20000000 ]
devmem 0x43c00024 32 1
sleep 1
[ "$(devmem 0x43c00024)" = 0x00000007 ]
echo '0 1' > "$debug/digital_tune"
"$checker" 10
/tmp/rtsctl mute
[ "$(devmem 0x43c00024)" = 0x00000007 ]
rx_check=$(spi_read 3);tx_check=$(spi_read 2)
[ $((rx_check & 3)) -eq 0 ] && [ $((tx_check & 3)) -eq 0 ]
qec_check=$(spi_read 0x16f)
[ "$(cat "$qec_mode")" = 1 ] && [ $(((qec_check >> 5) & 7)) -eq 4 ]
echo "Fast radio configured: $actual samples/s, 20 MHz bandwidth, targets muted"
complete=1
