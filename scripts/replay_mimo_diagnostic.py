"""Reprocess the captured MIMO waveform with stock versus expanded range grids."""
import sys,json,os,argparse
from pathlib import Path
import numpy as np
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pyespargos',default=os.environ.get('PYESPARGOS_PATH',str(Path(__file__).resolve().parents[2]/'ESPARGOS/pyespargos')))
parser.add_argument('--capture',type=Path,default=Path('build/diagnostics/mimo20-safe.npz'))
args=parser.parse_args()
espargos=Path(args.pyespargos)
sys.path[:0]=[str(espargos/'demos/iq/mimo-radar'),str(espargos)]
import mimo_processing as m
root=args.capture.parent;d=np.load(args.capture);fs=float(d['sample_rate']);fc=float(d['frequency'])
positions=np.array([[x,y] for y in range(2) for x in range(4)])*m.C/(2*fc)
ref=d['reference'];valid=abs(ref)>1e-6
b=np.fft.fft(d['baseline'],axis=-1).mean(axis=0)
h=np.ones_like(b);h[:,valid]=b[:,valid]/ref[valid];correction=np.conj(h)/(abs(h)+1e-9)
results=[]
for maximum in [60,900]:
 m.Sampling.range_maximum=property(lambda self,maximum=maximum:maximum)
 p=m.MIMOProcessor(positions,fc,sample_rate=fs)
 for iq,tick in zip(d['iq'][-p.history:],d['ticks'][-p.history:]):p.push(p.channels(iq,correction),int(tick))
 maps=p.maps();rd=maps[0];ri,vi=np.unravel_index(np.argmax(rd),rd.shape)
 results.append(dict(range_window_m=maximum,peak_range_m=float(p.ranges[ri]),peak_velocity_m_s=float(p.velocities[vi]),peak_map_db=float(rd[ri,vi])))
(root/'mimo-processor-replay.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))
