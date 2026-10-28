#!/usr/bin/env python3
"""Source-off noise through the complete antenna/ESPARGOS receiver chain.

Raw chunk PSDs retain noise that coherent accumulation would suppress. Power
is in receiver sample units, not calibrated dBm or a Pluto noise specification.
"""
import argparse,json
from pathlib import Path
import numpy as np

def analyze(path):
 d=np.load(path);settings=json.loads(str(d['capture_settings']))
 if not settings.get('source_off') or not settings.get('raw_burst_chunks'):
  raise ValueError('Expected unaveraged source-off recording')
 fs=float(d['sample_rate']);n=d['iq'].shape[-1];w=np.hanning(n);f=np.fft.fftfreq(n,1/fs)
 spectra=[]
 for key in ('baseline','iq'):
  x=d[key];x=x-x.mean(axis=-1,keepdims=True)
  spectra.append(np.mean(abs(np.fft.fft(x*w,axis=-1))**2,axis=(0,1))/sum(w*w))
 off,on=spectra;state=json.loads(str(d['fpga_status']));radio=json.loads(str(d['radio_profile']))
 report=dict(capture=str(path),pluto_sample_rate_hz=state['sample_rate_hz'],receiver_sample_rate_hz=fs,
  raw_chunks=len(d['iq']),baseline_chunks=len(d['baseline']),receiver_peak=float(d['peaks'].max()),
  fpga_clipped=state['clipped'],adc_snapshot=radio.get('adc_snapshot'),
  transceiver_overflow_start=radio.get('overflow_start'),transceiver_overflow_end=radio.get('overflow_end'),bands=[])
 for lo,hi in ((1,10),(10,20),(20,35)):
  mask=(abs(f)>=lo*1e6)&(abs(f)<hi*1e6)
  a,b=float(on[mask].mean()),float(off[mask].mean())
  report['bands'].append(dict(abs_offset_mhz=[lo,hi],active_power=a,muted_power=b,active_over_muted_db=float(10*np.log10(a/b))))
 report['scope']='Whole antenna/receiver chain; includes receiver noise, coupling and feedback; no intrinsic-device deembedding'
 return report,(f,off,on)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('captures',nargs='+',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 fig,axes=plt.subplots(len(a.captures),1,figsize=(11,3*len(a.captures)),squeeze=False);reports=[]
 for path,ax in zip(a.captures,axes[:,0]):
  report,(f,off,on)=analyze(path);reports.append(report)
  for spectrum,label in ((off,'Targets muted'),(on,'Target active, source off')):
   ax.plot(np.fft.fftshift(f)/1e6,np.fft.fftshift(10*np.log10(spectrum)),label=label)
  ax.set(title=path.stem,xlabel='RF offset (MHz)',ylabel='Receiver PSD (relative dB)');ax.grid(alpha=.2);ax.legend()
 fig.tight_layout();a.output.parent.mkdir(parents=True,exist_ok=True);fig.savefig(a.output.with_suffix('.png'),dpi=150)
 a.output.write_text(json.dumps(reports,indent=2)+'\n')
 for r in reports:print(r['capture'],[(b['abs_offset_mhz'],round(b['active_over_muted_db'],3)) for b in r['bands']])
if __name__=='__main__':main()
