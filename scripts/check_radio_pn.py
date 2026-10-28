#!/usr/bin/env python3
"""Sustained ADI RX PRBS and TX->RX digital-loopback checks at current clock.

Does not change sampling rates. Restores test/source controls; leaves TX at -60 dB.
"""
import argparse,json,time,sys
from pathlib import Path
import adi
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--seconds',type=float,default=5)
p.add_argument('--stress-bank',action='store_true',help='Run all four target paths at high NCO activity during the PN checks')
p.add_argument('--sweep-tx',action='store_true',help='Also scan TX clock/data delays; restore the selected delay afterward')
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
if not 0 < a.seconds <= 1800:p.error('--seconds must be in (0, 1800]')
r=adi.Pluto('ip:192.168.4.1');r.tx_hardwaregain_chan0=-60
class FPGARegisters:
 def __init__(self,device): self.device=device
 def reg_read(self,address): return self.device.reg_read(0x80000000 | address)
 def reg_write(self,address,value): self.device.reg_write(0x80000000 | address,value)
# ADC debug accesses require the PCORE magic bit; otherwise the driver routes
# to converter SPI access and this AD9361 driver silently returns zeros.
rx=FPGARegisters(r._ctx.find_device('cf-ad9361-lpc'));tx=r._txdac;phy=r._ctrl
saved=[(d,addr,d.reg_read(addr)) for d,addrs in [(rx,[0x400,0x440,0x418,0x458]),(tx,[0x418,0x458,0x414,0x454])] for addr in addrs]
old_prbs=phy.debug_attrs['bist_prbs'].value;old_loop=phy.debug_attrs['loopback'].value
controller=None;original_targets=None
if a.stress_bank:
 sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host'))
 from server import Controller
 controller=Controller(argparse.Namespace(demo=False,pluto='192.168.4.1',sample_rate=122880000,frequency=r.rx_lo))
 original_targets=controller.call('status')
 r.tx_hardwaregain_chan0=-89.75
 controller.call('apply','15\n0 305419896 4096\n1 591751049 4096\n17 2309737967 4096\n2047 2557891634 4096\n')

result={'sample_rate_hz':r._get_iio_attr('voltage0','sampling_frequency',False),'seconds_per_test':a.seconds,'delay_registers':{str(x):phy.reg_read(x) for x in (6,7)}}
result['digital_io_control']=phy.reg_read(0x3b)
result['rx_iodelay']=[rx.reg_read(0x800+4*lane) for lane in range(13)]
try:
 for mode in ('rx','tx_loopback'):
  phy.debug_attrs['bist_prbs'].value='0'
  # Match ADI's tuner: reset the ADC interface between RX BIST and TX loopback.
  rx.reg_write(0x40,2);rx.reg_write(0x40,3)
  tx.reg_write(0x40,3)
  phy.debug_attrs['loopback'].value='0' if mode=='rx' else '1'
  for ch in range(2):
   rx.reg_write(0x400+ch*64,0x251)
   rx.reg_write(0x418+ch*64,0 if mode=='rx' else 9<<16)
   if mode!='rx':
    tx.reg_write(0x418+ch*64,9)
    tx.reg_write(0x414+ch*64,0)
  tx.reg_write(0x44,1)
  if mode=='rx':phy.debug_attrs['bist_prbs'].value='2'
  # The ADI tuner also cycles ENSM around timing changes. Switching BIST
  # sources live can leave the port framing unlocked despite a good eye.
  phy.attrs['ensm_mode'].value='alert'
  phy.attrs['ensm_mode'].value='fdd'
  time.sleep(.1)
  acquisition=[]
  if mode=='tx_loopback':
   # A live BIST/loopback switch can lose port framing. Reapply the already
   # qualified clock-delay setting through the same phase transition used by
   # the timing sweep. Acquire once BEFORE the test; never retrain or clear
   # sticky errors during the measured interval.
   selected=phy.reg_read(7)
   for attempt in range(5):
    for ch in range(2):rx.reg_write(0x404+ch*64,7)
    time.sleep(.05)
    status=[rx.reg_read(0x404+ch*64) for ch in range(2)]
    acquisition.append(status)
    if not any(v&6 for v in status):break
    if attempt<4:
     phy.reg_write(7,0 if selected else 0xf0)
     time.sleep(.01)
     phy.reg_write(7,selected)
     time.sleep(.05)
  if controller is not None:
   controller.call('apply','15\n0 305419896 4096\n1 591751049 4096\n17 2309737967 4096\n2047 2557891634 4096\n')
   time.sleep(.01)
  for ch in range(2):rx.reg_write(0x404+ch*64,7)
  samples=[];start=time.monotonic()
  print(f'{mode}: checking for {a.seconds:g} seconds without clearing errors',flush=True)
  while time.monotonic()-start<a.seconds:
   time.sleep(min(.5,max(.001,a.seconds-(time.monotonic()-start))))
   samples.append({'elapsed':time.monotonic()-start,'status':[rx.reg_read(0x404+ch*64) for ch in range(2)]})
   if any(v&6 for v in samples[-1]['status']):break
  result[mode]={'channel_status':[rx.reg_read(0x404+ch*64) for ch in range(2)],'global_status':rx.reg_read(0x5c),'samples':samples,'acquisition':acquisition}
  if controller is not None:result[mode]['fpga_status']=controller.call('status')
  print(f"{mode}: {samples[-1]['elapsed']:.3f} seconds, status {result[mode]['channel_status']}, global {result[mode]['global_status']}",flush=True)
  if mode=='tx_loopback' and a.sweep_tx:
   selected=phy.reg_read(7);sweep=[]
   try:
    for delay in list(range(16))+[n<<4 for n in range(1,16)]:
     phy.reg_write(7,delay);time.sleep(.02)
     for ch in range(2):rx.reg_write(0x404+ch*64,7)
     time.sleep(.2)
     sweep.append({'delay_register':delay,'status':[rx.reg_read(0x404+ch*64) for ch in range(2)]})
   finally:phy.reg_write(7,selected)
   result['tx_sweep']=sweep
finally:
 phy.debug_attrs['bist_prbs'].value=old_prbs
 phy.debug_attrs['loopback'].value=old_loop
 for dev,addr,value in saved:dev.reg_write(addr,value)
 rx.reg_write(0x40,2);rx.reg_write(0x40,3)
 tx.reg_write(0x44,1)
 if controller is not None and original_targets is not None:
  lines=[str(original_targets['mask'])]+[f"{t['delay_samples']} {t['phase_increment']&0xffffffff} {t['gain_q15']}" for t in original_targets['targets']]
  controller.call('apply','\n'.join(lines)+'\n')
a.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:({kk:vv for kk,vv in v.items() if kk!='samples'} if k in ('rx','tx_loopback') else v) for k,v in result.items()},indent=2))
assert all(not any(v&6 for v in result[m]['channel_status']) and result[m]['global_status']&1 for m in ('rx','tx_loopback')),'PN errors detected'

if a.stress_bank:assert all(not result[m]['fpga_status']['clipped'] for m in ('rx','tx_loopback')),'FPGA arithmetic clipped under bounded stress'
