#!/usr/bin/env python3
"""Tune all 13 CMOS RX input lanes against RX PN, starting from a clean common setting.
No radio-rate changes. Retain selected delays only with --apply; otherwise restore.
"""
import argparse,json,time
from pathlib import Path
import adi
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--delay',type=lambda x:int(x,0),required=True)
p.add_argument('--common-tap',type=int,default=0)
p.add_argument('--apply',action='store_true')
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
if not 0<=a.delay<=255 or not 0<=a.common_tap<=31:p.error('Delay values out of range')
r=adi.Pluto('ip:192.168.4.1');r.tx_hardwaregain_chan0=-60;phy=r._ctrl;adc=r._ctx.find_device('cf-ad9361-lpc')
def read(x):return adc.reg_read(0x80000000|x)
def write(x,v):adc.reg_write(0x80000000|x,v)
def check(seconds=.05):
 time.sleep(.01)
 for ch in range(2):write(0x404+64*ch,7)
 time.sleep(seconds)
 status=[read(0x404+64*ch) for ch in range(2)];glob=read(0x5c)
 return {'status':status,'global_status':glob,'clean':not any(x&6 for x in status) and bool(glob&1)}
old_rx=phy.reg_read(6);old_prbs=phy.debug_attrs['bist_prbs'].value;old_loop=phy.debug_attrs['loopback'].value
regs={x:read(x) for x in [0x400,0x440,0x418,0x458,*range(0x800,0x834,4)]}
result={'sample_rate_hz':r._get_iio_attr('voltage0','sampling_frequency',False),'rx_delay':a.delay,'common_tap':a.common_tap,'lanes':[],'applied':False}
success=False
try:
 phy.debug_attrs['loopback'].value='0';phy.debug_attrs['bist_prbs'].value='2'
 for ch in range(2):write(0x400+ch*64,0x251);write(0x418+ch*64,0)
 for lane in range(13):write(0x800+lane*4,a.common_tap)
 phy.attrs['ensm_mode'].value='alert';phy.reg_write(6,a.delay);phy.attrs['ensm_mode'].value='fdd'
 write(0x40,2);write(0x40,3);time.sleep(.1)
 result['initial']=check(.5);assert result['initial']['clean'],'Initial common setting is not clean'
 for lane in range(13):
  sweep=[]
  for tap in range(32):
   write(0x800+lane*4,tap);sweep.append({'tap':tap,**check()})
  runs=[];start=0
  while start<32:
   if not sweep[start]['clean']:start+=1;continue
   end=start+1
   while end<32 and sweep[end]['clean']:end+=1
   runs.append((end-start,start));start=end
  assert runs,f'No clean eye for lane {lane}'
  width,start=max(runs);selected=start+(width-1)//2
  result['lanes'].append({'lane':lane,'window_start':start,'window_width':width,'selected':selected,'sweep':sweep})
  assert width>=3,f'Insufficient eye width for lane {lane}: {width}'
  write(0x800+lane*4,selected)
  verified=check(.2);result['lanes'][-1]['verification']=verified
  assert verified['clean'],f'Selected setting failed verification on lane {lane}'
  print(f'RX lane {lane}: {width} clean taps, selected {selected}',flush=True)
 result['final']=check(5);assert result['final']['clean'],'Final PN check failed'
 success=True
finally:
 if not (a.apply and success):
  phy.attrs['ensm_mode'].value='alert';phy.reg_write(6,old_rx);phy.attrs['ensm_mode'].value='fdd'
  for addr,value in regs.items():write(addr,value)
 else:
  for addr,value in regs.items():
   if addr<0x800:write(addr,value)
  result['applied']=True
 phy.debug_attrs['bist_prbs'].value=old_prbs;phy.debug_attrs['loopback'].value=old_loop
 write(0x40,2);write(0x40,3)
 a.output.write_text(json.dumps(result,indent=2)+'\n')
