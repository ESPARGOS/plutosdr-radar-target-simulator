#!/usr/bin/env python3
"""Prepare a 128..160 MSa/s interface experiment through a calibrated /2 FIR chain.

Requires a separately timing-qualified FPGA and disabled clock conditioner.
The FIR is bypassed in hardware after calibration; its driver cache remains 1.
This is a laboratory profile, not a firmware startup configuration.
"""
import argparse,json,time
from pathlib import Path
import adi
from clock_conditioner import control
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--rate',type=int,choices=(128000000,136000000,144000000,149760000,150000000,160000000))
p.add_argument('--qualified-fpga-max-rate',type=int)
p.add_argument('--restore',type=Path,help='Restore the calibrated base chain saved in this profile JSON')
p.add_argument('--output',type=Path)
p.add_argument('--minimal-filters',action='store_true',help='RX HB3 only, TX halfbands bypassed; converter clocks are half the standard fast profile')
p.add_argument('--no-halfbands',action='store_true',help='Bypass every RX/TX halfband, with both converters at the interface rate')
p.add_argument('--bandwidth',type=int,choices=(20000000,40000000,56000000),default=20000000,help='Experimental analog bandwidth; above 20 MHz exceeds AD9363 specification')
a=p.parse_args()
if a.minimal_filters and a.no_halfbands:p.error('Choose only one alternate filter profile')
control(False) # Keep the MMCM reset throughout rate/profile changes.
r=adi.Pluto('ip:192.168.4.1');r.tx_hardwaregain_chan0=-60
if a.restore:
 saved=json.loads(a.restore.read_text())
 r._ctrl.attrs['ensm_mode'].value='alert'
 try:
  for reg in (3,2):r._ctrl.reg_write(reg,saved['calibrated_registers'][str(reg)])
  if 'original_digital_io_control' in saved:r._ctrl.reg_write(0x3b,saved['original_digital_io_control'])
 finally:r._ctrl.attrs['ensm_mode'].value='fdd'
 # Raw SPI changes do not propagate cached parent clock rates automatically.
 # Read complete chains (parent to child) before the driver's FIR validator.
 restored_rx=r._ctrl.attrs['rx_path_rates'].value
 restored_tx=r._ctrl.attrs['tx_path_rates'].value
 r._set_iio_attr('out','voltage_filter_fir_en',False,0)
 r._set_iio_attr('voltage0','sampling_frequency',False,61440000)
 r.rx_rf_bandwidth=r.tx_rf_bandwidth=20000000
 print(r._ctrl.attrs['rx_path_rates'].value);print(r._ctrl.attrs['tx_path_rates'].value)
 raise SystemExit(0)
if not a.rate or not a.output or not a.qualified_fpga_max_rate:p.error('Specify rate, output, and timing-qualified FPGA maximum rate')
if a.rate>a.qualified_fpga_max_rate:p.error('Requested rate exceeds FPGA timing qualification')
if r._get_iio_attr('voltage0','sampling_frequency',False)>61440100:raise RuntimeError('Restore a normal radio profile first')
r._set_iio_attr('out','voltage_filter_fir_en',False,0)
original_digital_io_control=r._ctrl.reg_read(0x3b)
base=a.rate//4
# Both converter clocks remain within the ADI driver limits (640/320 MHz).
# Before bypass: RX /2 /2 /2 FIR/2, TX FIRx2 x1 x2 x2.
rx=[base*32,base*16,base*8,base*4,base*2,base]
tx=[base*32,base*8,base*4,base*2,base*2,base]
if a.minimal_filters:
 rx=[base*32,base*8,base*4,base*2,base*2,base]
 tx=[base*32,base*4,base*4,base*2,base*2,base]
if a.no_halfbands:
 rx=[base*32,base*4,base*4,base*2,base*2,base]
 tx=[base*32,base*4,base*4,base*2,base*2,base]
assert rx[1]<=640000000 and tx[1]<=320000000
fir=('TX 3 GAIN 0 INT 2\nRX 3 GAIN 0 DEC 2\n'
     +'RTX '+' '.join(map(str,tx))+'\nRRX '+' '.join(map(str,rx))
     +f'\nBWRX {a.bandwidth}\nBWTX {a.bandwidth}\n32767,32767\n'+'0,0\n'*15)
r._ctrl.attrs['filter_fir_config'].value=fir
r._set_iio_attr('out','voltage_filter_fir_en',False,1)
before={str(reg):r._ctrl.reg_read(reg) for reg in (2,3,6,7)}
result={'requested_rate':a.rate,'minimal_filters':a.minimal_filters,'no_halfbands':a.no_halfbands,'requested_bandwidth':a.bandwidth,'original_digital_io_control':original_digital_io_control,'calibrated_registers':before,'calibrated_rx':r._ctrl.attrs['rx_path_rates'].value,'calibrated_tx':r._ctrl.attrs['tx_path_rates'].value}
a.output.write_text(json.dumps(result,indent=2)+'\n') # Recovery data precedes raw changes.
r._ctrl.attrs['ensm_mode'].value='alert'
try:
 r._ctrl.reg_write(3,before['3'] & ~(11 if a.minimal_filters or a.no_halfbands else 7)) # RX FIR and HB1 bypass.
 r._ctrl.reg_write(2,before['2'] & ~11) # TX FIR and HB2 bypass.
finally:r._ctrl.attrs['ensm_mode'].value='fdd'
result.update(rx_path_rates=r._ctrl.attrs['rx_path_rates'].value,tx_path_rates=r._ctrl.attrs['tx_path_rates'].value,
 sampling_frequency=r._get_iio_attr('voltage0','sampling_frequency',False),driver_fir_enabled=r._get_iio_attr('out','voltage_filter_fir_en',False),rx_rf_bandwidth=r.rx_rf_bandwidth,tx_rf_bandwidth=r.tx_rf_bandwidth,
 registers={str(reg):r._ctrl.reg_read(reg) for reg in (2,3,6,7)})
a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
assert abs(result['sampling_frequency']-a.rate)<100
assert all(result['registers'][str(reg)]&3==0 for reg in (2,3))
