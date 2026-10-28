#!/usr/bin/env python3
"""Doppler-tagged two-tone distortion comparison from independent ESPARGOS IQ.

Reports observed spur powers AND nearby-Doppler floors; does not subtract noise
or equate a floor-limited measurement with the device's intrinsic distortion.
The historical rx_image/tx_image names classify Doppler sign, not exclusive
physical origin: ESPARGOS TX images also enter the positive-tag group, and its
RX image of the returned echo also enters the negative-tag group. Coherent
image terms can reinforce or cancel as radio LO/calibration phases change.
"""
import argparse,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('captures',nargs='+',type=Path)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args();results=[]
fig,ax=plt.subplots(figsize=(11,5))
for path in a.captures:
 d=np.load(path);settings=json.loads(str(d['capture_settings']))
 if not settings.get('two_tone'):raise ValueError(f'{path} is not a two-tone capture')
 fundamentals=list(map(int,d['bins']));assert len(fundamentals)==2
 lo,hi=sorted(fundamentals);images=[-lo,-hi];intermods=[2*lo-hi,2*hi-lo]
 state=json.loads(str(d['fpga_status']));fs=float(d['sample_rate']);n=d['iq'].shape[-1]
 tick=np.unwrap(d['ticks'].astype(float)*2*np.pi/(1<<24))*(1<<24)/(2*np.pi)
 t=(tick-tick[0])*256/fs
 x=np.fft.fft(d['iq'],axis=-1);x-=x.mean(axis=0,keepdims=True)
 w=np.hanning(len(x));tag=state['targets'][0]['phase_increment']*state['sample_rate_hz']/2**32
 def spectrum(f):
  z=np.einsum('t,tak->ak',w*np.exp(-2j*np.pi*f*t),x)/w.sum()
  return np.mean(abs(z)**2,axis=0)
 def group(power,bins):return float(np.sum(power[np.array(bins)%n]))
 echo=spectrum(tag);floor=(spectrum(tag+5)+spectrum(tag-5))/2
 reference=group(echo,fundamentals)
 def dbc(value):return float(10*np.log10(max(value,1e-30)/max(reference,1e-30)))
 groups={'imd3':intermods,'rx_image':images}
 report=dict(capture=str(path),fundamental_bins=fundamentals,sample_rate_hz=state['sample_rate_hz'],tag_hz=tag,
  fpga_clipped=state['clipped'],esp_peak=float(d['peaks'].max()),
  fundamental_power=reference,fundamental_floor_dbc=dbc(group(floor,fundamentals)))
 report['measurement_scope']='Complete antenna/ESPARGOS/Pluto chain; image groups are Doppler-sign classes, not isolated transceiver errors'
 if 'radio_profile' in d:
  radio=json.loads(str(d['radio_profile']))
  report['transceiver_overflow_start']=radio.get('overflow_start')
  report['transceiver_overflow_end']=radio.get('overflow_end')
  if radio.get('image_grid_alignment'):
   # The LO is aligned to half a bin, so Pluto mirrors fall one bin below
   # the nominal negative tones. Sum powers without slow-time averaging:
   # oscillator drift must not erase the image being measured.
   from analyze_raw_spurs import adc_offset
   offset,ratio=adc_offset(d['pluto_input'],state['sample_rate_hz'],np.asarray(fundamentals)*fs/n)
   shifted=[-b-1 for b in fundamentals]
   active=np.mean(abs(np.fft.fft(d['iq'],axis=-1))**2,axis=(0,1))
   muted=np.mean(abs(np.fft.fft(d['baseline'],axis=-1))**2,axis=(0,1))
   on=group(active,shifted);off=group(muted,shifted)
   offsets=[offset]+[entry['offset_hz'] for entry in radio.get('image_grid_tracking',[])]
   residual=np.array(offsets)*2-fs/n
   duration=settings.get('accumulation_chunks',1024)*256/fs
   response=np.abs(np.sinc((residual[:,None]+np.array([-tag,tag]))*duration))
   report['shifted_pluto_images']={'bins':shifted,'active_dbc':dbc(on),'muted_dbc':dbc(off),
    'excess_dbc':dbc(on-off) if on>off else None,'end_offset_hz':offset,
    'desired_offset_hz':fs/n/2,'clock_ratio':ratio,
    'sampled_worst_averaging_loss_db':float(-20*np.log10(max(response.min(),1e-30))),
    'offset_tracking':radio.get('image_grid_tracking',[]),
    'scope':'Combined Pluto RX/TX images, noncoherent power after short hardware accumulation; includes receiver noise and phase-noise skirts'}
 for name,bins in groups.items():
  report[name+'_dbc']=dbc(group(echo,bins));report[name+'_floor_dbc']=dbc(group(floor,bins))
 image=spectrum(-tag);imagefloor=(spectrum(-tag+5)+spectrum(-tag-5))/2
 report['tx_image_dbc']=dbc(group(image,images));report['tx_image_floor_dbc']=dbc(group(imagefloor,images))
 if 'pluto_input' in d and len(d['pluto_input']):
  raw=d['pluto_input'];levels=np.r_[abs(raw.real),abs(raw.imag)]
  report['pluto_input_peak']=float(levels.max());report['pluto_input_fullscale_fraction']=float(np.mean(levels>=2047))
 results.append(report)
 ax.plot(np.fft.fftshift(np.fft.fftfreq(n,1/fs))/1e6,np.fft.fftshift(10*np.log10((echo+1e-30)/reference)),label=path.stem)
ax.set(xlabel='Baseband frequency (MHz)',ylabel='Tagged response / combined fundamental (dBc)',ylim=(-85,5))
ax.grid(alpha=.2);ax.legend();fig.tight_layout()
a.output.parent.mkdir(parents=True,exist_ok=True)
a.output.write_text(json.dumps(results,indent=2)+'\n');fig.savefig(a.output.with_suffix('.png'),dpi=150)
print(json.dumps(results,indent=2))
