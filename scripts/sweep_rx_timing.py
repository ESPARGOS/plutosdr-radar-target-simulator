#!/usr/bin/env python3
"""Laboratory RX PN sweep of all 13 CMOS input lanes and AD9363 interface delay.
Restores original delays and test state. No sample-rate change or RF transmission.
"""
import argparse,json,time
from pathlib import Path
import adi
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--common-taps',type=int,nargs='+',default=[0,8,16,24,31])
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
if any(not 0<=x<=31 for x in a.common_taps):p.error('IDELAY taps must be 0..31')
r=adi.Pluto('ip:192.168.4.1');r.tx_hardwaregain_chan0=-60;phy=r._ctrl;adc=r._ctx.find_device('cf-ad9361-lpc')
def read(x):return adc.reg_read(0x80000000|x)
def write(x,v):adc.reg_write(0x80000000|x,v)
old_rx=phy.reg_read(6);old_prbs=phy.debug_attrs['bist_prbs'].value;old_loop=phy.debug_attrs['loopback'].value
regs={x:read(x) for x in [0x400,0x440,0x418,0x458,*range(0x800,0x834,4)]}
result={'sample_rate_hz':r._get_iio_attr('voltage0','sampling_frequency',False),'original_rx_delay':old_rx,'original_iodelay':[regs[x] for x in range(0x800,0x834,4)],'settle_seconds':.05,'check_seconds':.05,'sweep':[]}
try:
 phy.debug_attrs['loopback'].value='0';phy.debug_attrs['bist_prbs'].value='2'
 for ch in range(2):write(0x400+ch*64,0x251);write(0x418+ch*64,0)
 write(0x40,2);write(0x40,3)
 for tap in a.common_taps:
  for lane in range(13):write(0x800+4*lane,tap)
  assert all(read(0x800+4*lane)==tap for lane in range(13)), 'IDELAY write/readback mismatch'
  passed=[]
  for delay in list(range(16))+[i<<4 for i in range(1,16)]:
   phy.attrs['ensm_mode'].value='alert';phy.reg_write(6,delay);phy.attrs['ensm_mode'].value='fdd'
   time.sleep(.05)
   for ch in range(2):write(0x404+ch*64,7)
   time.sleep(.05)
   status=[read(0x404+ch*64) for ch in range(2)];global_status=read(0x5c)
   clean=not any(x&6 for x in status) and bool(global_status&1)
   result['sweep'].append({'common_tap':tap,'delay':delay,'status':status,'global_status':global_status,'clean':clean})
   if clean:passed.append(hex(delay))
  print(f'IDELAY {tap}: clean settings {passed}',flush=True)
finally:
 phy.attrs['ensm_mode'].value='alert';phy.reg_write(6,old_rx);phy.attrs['ensm_mode'].value='fdd'
 phy.debug_attrs['bist_prbs'].value=old_prbs;phy.debug_attrs['loopback'].value=old_loop
 for addr,value in regs.items():write(addr,value)
 write(0x40,2);write(0x40,3)
 a.output.write_text(json.dumps(result,indent=2)+'\n')
