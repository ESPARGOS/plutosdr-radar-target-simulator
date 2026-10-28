#!/usr/bin/env python3
"""Launch the existing MIMO demo with Pluto-compatible bandwidth and range.
No ESPARGOS source files are modified. Other demo CLI arguments pass through.
"""
import argparse,runpy,sys,json,urllib.request,os
from pathlib import Path
p=argparse.ArgumentParser(add_help=False)
p.add_argument('--pyespargos',default=os.environ.get('PYESPARGOS_PATH',str(Path(__file__).resolve().parents[2]/'ESPARGOS/pyespargos')))
p.add_argument('--host',default=os.environ.get('ESPARGOS_HOST','192.168.1.100'))
p.add_argument('--pluto',default='192.168.4.1')
p.add_argument('--range-max',type=float,default=900,help='Displayed range in metres, including Pluto latency')
a,remaining=p.parse_known_args()
if not 0<a.range_max<950:p.error('--range-max must be between 0 and 950 m (20 MSa/s pilot ambiguity)')
root=Path(a.pyespargos);demo=root/'demos/iq/mimo-radar'
sys.path[:0]=[str(demo),str(root)]
state=json.load(urllib.request.urlopen(f'http://{a.pluto}/cgi-bin/radar.cgi/state',timeout=5))
carrier=state['frequency_hz']/1e6
sys.argv=[str(demo/'main.py'),'-s',a.host,'-o',f'app.frequency={carrier}','-o','app.sample_rate=20','-o',f'app.range_maximum={a.range_max}','-o','app.amplitude=0.08','-o','app.rx_gain=15',*remaining]
runpy.run_path(str(demo/'main.py'),run_name='__main__')
