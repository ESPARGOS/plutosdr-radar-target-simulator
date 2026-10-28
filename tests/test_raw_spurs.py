"""Validate measurement math against known off-grid tones and dropped chunks."""
import importlib.util
import json
from pathlib import Path
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('raw_spurs',ROOT/'scripts/analyze_raw_spurs.py')
raw=importlib.util.module_from_spec(spec);spec.loader.exec_module(raw)

class RawSpurTests(unittest.TestCase):
 def test_frequency_offset(self):
  fs=160e6;t=np.arange(65536)/fs;tones=np.array([13,31])*20e6/256
  ratio=1.000012;offset=33400.25
  x=sum(np.exp(2j*np.pi*ratio*(f+offset)*t) for f in tones)
  measured,clock=raw.adc_offset(x,fs,tones)
  self.assertAlmostEqual(measured,offset,delta=.1)
  self.assertAlmostEqual(clock,ratio,delta=1e-7)

 def test_missing_chunks_and_wrap(self):
  ticks=np.concatenate([np.arange(16)+i*8192+(1<<24)-100 for i in range(24)])
  iq=np.broadcast_to(ticks[:,None,None],(len(ticks),1,256)).copy()
  windows,starts=raw.bursts(iq,ticks%(1<<24))
  self.assertEqual(len(windows),48)
  self.assertTrue(np.all(np.diff(starts)>0))
  np.testing.assert_array_equal(windows[0,0,::256],ticks[:8])
  with self.assertRaises(ValueError):raw.bursts(iq,np.zeros(len(ticks)))

 def test_known_shifted_mirror(self):
  fs=20e6;bins=np.array([13,31]);tones=bins*fs/256;offset=fs/256/2
  ticks=np.concatenate([np.arange(8)+i*8192 for i in range(300)])
  t=(ticks[:,None]*256+np.arange(256))/fs;tag=17
  desired=sum(np.exp(2j*np.pi*f*t) for f in tones)
  mirror=.02*sum(np.exp(2j*np.pi*(-f-2*offset)*t) for f in tones)
  baseline=(3*desired)[:,None,:]
  iq=baseline+(desired*np.exp(2j*np.pi*tag*t)+mirror)[:,None,:]
  adc_t=np.arange(65536)/fs
  adc=sum(np.exp(2j*np.pi*(f+offset)*adc_t) for f in tones)
  path=ROOT/'build/tests/raw-spurs-synthetic.npz';path.parent.mkdir(parents=True,exist_ok=True)
  np.savez(path,iq=iq,ticks=ticks,baseline=baseline,baseline_ticks=ticks,
   capture_settings=json.dumps(dict(raw_burst_chunks=16,two_tone=True)),
   fpga_status=json.dumps(dict(sample_rate_hz=fs,clipped=False,targets=[dict(phase_increment=tag*2**32/fs)])),
   radio_profile='{}',sample_rate=fs,bins=bins,reference=np.zeros(256),pluto_input=adc,peaks=np.array([10]))
  try:
   result,_=raw.analyze(path)
   self.assertAlmostEqual(result['shifted_pluto_images']['active_dbc'],20*np.log10(.02),delta=.15)
  finally:path.unlink()

if __name__=='__main__':unittest.main()
