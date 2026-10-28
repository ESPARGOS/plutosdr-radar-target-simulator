#!/usr/bin/env python3
"""Volatile 122.88 MHz experiment; requires the prepared fast-interface FPGA.

Do not run with the normal two-cycle bitstream. Exceeds AD9363 CMOS timing
specifications. Reboot restores the installed firmware and normal clock profile.
"""
import argparse,json
from pathlib import Path
import adi
from experimental_filter_profile import configure
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--fast-fpga-loaded',action='store_true',required=True)
p.add_argument('--base-rate',type=int,choices=(50000000,55000000,60000000,61440000),default=61440000,help='Driver-supported base rate; actual rate is twice this')
p.add_argument('--wide',action='store_true')
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
base=configure('rx-no-hb1' if a.wide else 'stock',56000000 if a.wide else 20000000,a.base_rate)
r=adi.Pluto('ip:192.168.4.1')
r.tx_hardwaregain_chan0=-60
before={str(x):r._ctrl.reg_read(x) for x in (2,3,6,7)}
r._ctrl.attrs['ensm_mode'].value='alert'
try:
 # Stock RX: bypass HB1; alternate wide RX: bypass HB2.
 # TX: bypass HB2. ADC/DAC clocks are unchanged.
 r._ctrl.reg_write(3,before['3'] & ~(8 if a.wide else 4))
 r._ctrl.reg_write(2,before['2'] & ~8)
finally:r._ctrl.attrs['ensm_mode'].value='fdd'
after={str(x):r._ctrl.reg_read(x) for x in (2,3,6,7)}
result=dict(base_profile=base,before=before,after=after,
 rx_path_rates=r._ctrl.attrs['rx_path_rates'].value,
 tx_path_rates=r._ctrl.attrs['tx_path_rates'].value,
 sampling_frequency=r._get_iio_attr('voltage0','sampling_frequency',False))
a.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
assert abs(result['sampling_frequency']-2*a.base_rate)<100
