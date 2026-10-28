#!/usr/bin/env python3
"""Control the experimental FPGA clock conditioner without changing RF rates.

Always disable it BEFORE changing sample-rate profiles. The multiplier-8 MMCM
uses 75..150 MHz input. Multiplier-6 experiments use 100..200 MHz;
0x1000d/0x10010 use multiplier 7. Only revision 0x10002+ safely disables.
"""
import argparse,json,subprocess,time,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def remote(command):
 env=os.environ.copy();env['SSHPASS']=env.get('PLUTO_PASSWORD','analog')
 return subprocess.check_output(['sshpass','-e','ssh','-F','/dev/null','-o','LogLevel=ERROR','-o','ConnectTimeout=5','-o',f'UserKnownHostsFile={ROOT}/build/known_hosts','root@192.168.4.1',command],env=env,text=True,timeout=10).strip()
def control(enable=None):
 version=int(remote('devmem 0x43c00004'),16)
 if version not in range(0x10001,0x1000e) and version!=0x10010:raise RuntimeError(f'Unknown clock-conditioner FPGA revision {version:#x}')
 if enable is False and version==0x10001:raise RuntimeError('This FPGA revision cannot safely disable its MMCM; load the repaired image')
 if enable is not None:
  if enable:
   import adi
   radio=adi.Pluto('ip:192.168.4.1');rate=radio._get_iio_attr('voltage0','sampling_frequency',False)
   multiplier=8 if version<=0x10006 or version==0x1000c else 7 if version in (0x1000d,0x10010) else 6
   minimum,maximum=600000000/multiplier,1200000000/multiplier+100
   if not minimum<=rate<=maximum:raise RuntimeError('Sample rate outside MMCM VCO operating range')
  remote(f'devmem 0x43c00024 32 {int(enable)}');time.sleep(.05)
 value=int(remote('devmem 0x43c00024'),16)
 result={'version':version,'control':value,'enabled':bool(value&1),'locked':bool(value&2),'running':bool(value&4) if version>=0x10002 else None}
 if enable is True and value&3!=3:raise RuntimeError(f'MMCM failed to lock: {result}')
 if enable is False and value!=0:raise RuntimeError(f'MMCM failed to stop: {result}')
 return result
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('status','enable','disable'));a=p.parse_args()
 print(json.dumps(control(None if a.action=='status' else a.action=='enable'),indent=2))
