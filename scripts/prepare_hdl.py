#!/usr/bin/env python3
"""Add the radar core and Pluto wiring to the pinned ADI HDL sources."""

from pathlib import Path
import re
import os
import subprocess

root = Path(__file__).resolve().parents[1]
hdl = root / "vendor/adi-hdl"
# The extracted vendor tree is not a Git checkout. Do not let git apply
# discover this project's parent repository and reinterpret patch paths.
patch_env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(hdl.parent)}
# Skip patches that are already applied. Stop if the sources do not match.
for name in (
    "adi-radar-low-latency.patch",
    "adi-radar-clock-conditioner.patch",
    "adi-radar-loopback-register.patch",
):
    patch = root / "patches" / name
    if subprocess.run(
        ["git", "apply", "--reverse", "--check", str(patch)],
        cwd=hdl,
        env=patch_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode:
        subprocess.run(["git", "apply", str(patch)], cwd=hdl, env=patch_env, check=True)
ip = hdl / "library/radar_axi"
ip.mkdir(exist_ok=True)


def write_if_changed(path, text):
    if not path.exists() or path.read_text() != text:
        path.write_text(text)


for f in (root / "rtl").iterdir():
    write_if_changed(ip / f.name, f.read_text())
write_if_changed(
    ip / "Makefile",
    "LIBRARY_NAME := radar_axi\nGENERIC_DEPS += radar_axi.sv target_bank.sv nco_rom.v\nXILINX_DEPS += radar_axi_ip.tcl radar_cdc.xdc\ninclude ../scripts/library.mk\n",
)
write_if_changed(
    ip / "radar_axi_ip.tcl",
    """source ../../scripts/adi_env.tcl
source $ad_hdl_dir/library/scripts/adi_ip_xilinx.tcl
adi_ip_create radar_axi
adi_ip_files radar_axi [list radar_axi.sv target_bank.sv nco_rom.v radar_cdc.xdc]
adi_ip_properties radar_axi
ipx::save_core [ipx::current_core]
""",
)
p = hdl / "projects/pluto/Makefile"
s = p.read_text()
if "LIB_DEPS += radar_axi" not in s:
    s = s.replace(
        "LIB_DEPS += axi_ad9361", "LIB_DEPS += radar_axi\nLIB_DEPS += axi_ad9361"
    )
    write_if_changed(p, s)
p = hdl / "projects/pluto/system_bd.tcl"
s = p.read_text().split("# RADAR TARGET SIMULATOR")[0]
# The simulator runs at the RF sample rate. Host-side optional filters are unused.
s = re.sub(r"ad_add_(?:interpolation|decimation)_filter[^\n]*\\\n[^\n]*\n", "", s)
s = (
    "\n".join(
        line
        for line in s.splitlines()
        if not any(
            x in line
            for x in (
                "rx_fir_decimator",
                "tx_fir_interpolator",
                "decim_slice",
                "interp_slice",
            )
        )
    )
    + "\n"
)
s += """# RADAR TARGET SIMULATOR
# Compile-time bypass removes pipeline registers, unlike runtime correction disable.
# The RF transceiver retains its own calibrated DC and IQ corrections.
# clk and l_clk are the same net on Pluto; this bypass is not a generic CDC.
ad_ip_parameter axi_ad9361 CONFIG.RADAR_LOW_LATENCY 1
ad_ip_parameter axi_ad9361 CONFIG.TDD_DISABLE 1
ad_ip_parameter axi_ad9361 CONFIG.DAC_DDS_DISABLE 1
ad_ip_parameter axi_ad9361 CONFIG.ADC_DATAFORMAT_DISABLE 1
ad_ip_parameter axi_ad9361 CONFIG.ADC_DCFILTER_DISABLE 1
ad_ip_parameter axi_ad9361 CONFIG.ADC_IQCORRECTION_DISABLE 1
ad_ip_parameter axi_ad9361 CONFIG.DAC_IQCORRECTION_DISABLE 1
ad_connect axi_ad9361/adc_enable_i0 cpack/enable_0
ad_connect axi_ad9361/adc_enable_q0 cpack/enable_1
ad_connect axi_ad9361/adc_data_i0 cpack/fifo_wr_data_0
ad_connect axi_ad9361/adc_data_q0 cpack/fifo_wr_data_1
ad_connect axi_ad9361/adc_valid_i0 cpack/fifo_wr_en
ad_connect axi_ad9361/dac_enable_i0 tx_upack/enable_0
ad_connect axi_ad9361/dac_enable_q0 tx_upack/enable_1
ad_connect axi_ad9361/dac_data_i0 tx_upack/fifo_rd_data_0
ad_connect axi_ad9361/dac_data_q0 tx_upack/fifo_rd_data_1
ad_connect axi_ad9361/dac_valid_i0 logic_or/Op1
ad_ip_instance radar_axi radar_targets
ad_connect radar_targets/clean_enable axi_ad9361/clean_enable
ad_connect radar_targets/clean_run axi_ad9361/clean_run
ad_connect axi_ad9361/clean_locked radar_targets/clean_locked
ad_connect axi_ad9361/l_clk radar_targets/sample_clk
ad_connect axi_ad9361/rst radar_targets/sample_reset
ad_connect axi_ad9361/adc_valid_i0 radar_targets/adc_valid
ad_connect axi_ad9361/adc_data_i0 radar_targets/adc_i
ad_connect axi_ad9361/adc_data_q0 radar_targets/adc_q
foreach chan {i0 q0} output {dac_i dac_q} {
  set pin [get_bd_pins axi_ad9361/dac_data_$chan]
  disconnect_bd_net [get_bd_nets -of_objects $pin] $pin
  ad_connect radar_targets/$output axi_ad9361/dac_data_$chan
}
ad_cpu_interconnect 0x43c00000 radar_targets
"""
write_if_changed(p, s)
