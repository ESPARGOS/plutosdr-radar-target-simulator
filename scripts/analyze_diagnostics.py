"""Compare MIMO echo bandwidth, delay ambiguity, and source-muted feedback."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
root=Path('build/diagnostics');summaries=[]
fig,axes=plt.subplots(2,2,figsize=(12,8))
for ax,name in zip(axes.flat,['mimo20-safe','mimo80-safe','mimo20-demo-gains','feedback-safe']):
 d=np.load(root/(name+'.npz'));fs=float(d['sample_rate']);bins=d['bins'];n=256
 tick=np.unwrap(d['ticks'].astype(float)*2*np.pi/(1<<24))*(1<<24)/(2*np.pi);t=(tick-tick[0])*256/fs
 h=np.fft.fft(d['iq'],axis=-1)[...,bins%n]/d['reference'][bins%n]
 b=np.fft.fft(d['baseline'],axis=-1)[...,bins%n]/d['reference'][bins%n]
 corr=np.conj(b.mean(axis=0))/(abs(b.mean(axis=0))+1e-12)
 h*=corr[None];h-=h.mean(axis=0,keepdims=True)
 window=np.hanning(len(t));echo=np.einsum('t,tak->ak',np.exp(-2j*np.pi*17*t)*window,h)/window.sum()
 freq=bins*fs/n/1e6;power=np.mean(abs(echo)**2,axis=0)
 # Separate interleaved transmitter pilots to avoid arbitrary cross-TX phase.
 delay=np.arange(4096)/4096*(n/fs/2)*1e6
 profiles=[]
 for parity in range(2):
  select=bins%2==parity
  matrix=np.exp(2j*np.pi*(bins[select]*fs/n)[:,None]*delay[None]*1e-6)
  profile=np.mean(abs((echo[:,select]*np.hanning(select.sum()))@matrix)**2,axis=0)
  profiles.append(profile)
 profile=np.mean(profiles,axis=0);peak_delay=float(delay[profile.argmax()]);snr=float(10*np.log10(profile.max()/np.median(profile)))
 fpga=json.loads(str(d['fpga_status']));peak=float(d['peaks'].max());baseline_rms=float(np.sqrt(np.mean(abs(d['baseline'])**2)));active_rms=float(np.sqrt(np.mean(abs(d['iq'])**2)))
 summary=dict(capture=name,fs_hz=fs,esp_peak=peak,esp_peak_dbfs=float(20*np.log10(peak/512)),fpga_clipped=fpga['clipped'],baseline_iq_rms=baseline_rms,active_iq_rms=active_rms,active_over_baseline_db=float(20*np.log10(active_rms/baseline_rms)),delay_peak_modulo_us=peak_delay,delay_ambiguity_us=n/fs/2*1e6,range_peak_modulo_m=peak_delay*149.896229,echo_peak_over_delay_median_db=snr)
 if fs>20e6:summary['outer_vs_inner_echo_power_db']=float(10*np.log10(np.mean(power[abs(freq)>15])/np.mean(power[abs(freq)<6])))
 summaries.append(summary)
 if name=='feedback-safe':
  ax.plot(np.arange(len(d['baseline'])),np.sqrt(np.mean(abs(d['baseline'])**2,axis=(1,2))),label='Pluto muted');ax.plot(np.arange(len(d['iq'])),np.sqrt(np.mean(abs(d['iq'])**2,axis=(1,2))),label='Target enabled');ax.set(xlabel='Capture',ylabel='Accumulated IQ RMS');ax.legend()
 else:
  ax.plot(delay*149.896229,10*np.log10(profile/profile.max()+1e-12));ax.axvspan(0,15*80e6/fs,color='orange',alpha=.25,label='Demo range display');ax.set(xlabel='Range modulo pilot ambiguity (m)',ylabel='17 Hz echo response (dB)',ylim=(-50,2));ax.legend()
 ax.set_title(name)
fig.tight_layout();fig.savefig(root/'mimo-diagnosis.png',dpi=150)
(root/'summary.json').write_text(json.dumps(summaries,indent=2)+'\n');print(json.dumps(summaries,indent=2))
