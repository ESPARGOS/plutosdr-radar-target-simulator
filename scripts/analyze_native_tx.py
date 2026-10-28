#!/usr/bin/env python3
"""Native TX-tone images, separated from the receiver's mirror by LO offset."""
import argparse,json
from pathlib import Path
import numpy as np
from scipy.optimize import minimize_scalar
from analyze_raw_spurs import bursts

def analyze(path):
 d=np.load(path);cfg=json.loads(str(d['capture_settings']));s=json.loads(str(d['fpga_status']))
 if cfg.get('pluto_bist_tone') is None or not cfg.get('raw_burst_chunks') or s['mask']:
  raise ValueError('Requires raw native TX tone with targets muted')
 fs=float(d['sample_rate']);nominal=s['sample_rate_hz']*(cfg['pluto_bist_tone']+1)/32
 x,_=bursts(d['iq'],d['ticks']);b,_=bursts(d['baseline'],d['baseline_ticks']);n=x.shape[-1]
 w=np.hanning(n);t=np.arange(n)/fs
 x=(x-x.mean(axis=-1,keepdims=True))*w/w.sum();b=(b-b.mean(axis=-1,keepdims=True))*w/w.sum()
 def power(a,f):return float(np.mean(abs(np.einsum('tak,k->ta',a,np.exp(-2j*np.pi*f*t)))**2))
 z=np.mean(abs(np.fft.fft(x,axis=-1))**2,axis=(0,1));freq=np.fft.fftfreq(n,1/fs)
 requested_offset=cfg.get('pluto_lo_offset_hz',0)
 candidates=np.flatnonzero(abs(abs(freq-requested_offset)-nominal)<150000);k=candidates[np.argmax(z[candidates])]
 nominal=float(np.copysign(nominal,freq[k]-requested_offset))
 fit=minimize_scalar(lambda f:-power(x,f),bounds=(freq[k]-fs/n,freq[k]+fs/n),method='bounded',options={'xatol':.1})
 actual=fit.x;offset=actual-nominal;reference=power(x,actual)
 if 2*abs(offset)<5*fs/n:raise ValueError('LO offset too small to separate TX and receiver images at this resolution')
 def dbc(p):return float(10*np.log10(max(p,1e-30)/reference))
 report=dict(capture=str(path),sample_rate_hz=s['sample_rate_hz'],windows=len(x),nominal_tone_hz=nominal,
  measured_tone_hz=actual,apparent_lo_offset_hz=offset,receiver_peak=float(d['peaks'].max()),
  tx_attenuation_db=cfg['pluto_tx_attenuation'],target_bank_muted=True)
 for label,f in [('pluto_tx_image',-nominal+offset),('espargos_rx_image',-actual),('pluto_lo',offset)]:
  on=power(x,f);off=power(b,f);floor=(power(x,f-3*fs/n)+power(x,f+3*fs/n))/2
  report[label]=dict(frequency_hz=f,power_dbc=dbc(on),muted_dbc=dbc(off),nearby_floor_dbc=dbc(floor),excess_dbc=dbc(on-off) if on>off else None)
 report['scope']='Native transceiver TX tone bypasses FPGA targets; RF antenna/receiver response remains; no calibrated intrinsic specification'
 return report

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('captures',nargs='+',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
 result=[analyze(path) for path in a.captures];a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
