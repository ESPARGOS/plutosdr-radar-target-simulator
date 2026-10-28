#!/usr/bin/env bash
set -euo pipefail
python3 tests/test_datapath.py
iverilog -g2012 -s tb_axi -o build/tests/axi rtl/radar_axi.sv rtl/target_bank.sv rtl/nco_rom.v tests/tb_axi.sv
vvp build/tests/axi
python3 tests/test_control.py
python3 tests/test_firmware_import.py
iverilog -g2012 -i -s tb_interface -o build/tests/interface tests/tb_interface.sv \
 vendor/adi-hdl/library/axi_ad9361/axi_ad9361.v \
 vendor/adi-hdl/library/axi_ad9361/axi_ad9361_tx_channel.v \
 vendor/adi-hdl/library/axi_ad9361/xilinx/axi_ad9361_cmos_if.v \
 vendor/adi-hdl/library/common/ad_iqcor.v
vvp build/tests/interface
