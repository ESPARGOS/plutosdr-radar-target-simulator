#!/usr/bin/env python3
"""Local hardware control UI. IQ never leaves the FPGA datapath."""
import argparse
import json
import math
import mimetypes
import os
from pathlib import Path
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[1]
MAX_TARGETS=4

def validate(payload,fs):
    if not isinstance(payload,dict) or not isinstance(payload.get('targets'),list):
        raise ValueError('Expected a targets array')
    if len(payload['targets'])>MAX_TARGETS:raise ValueError('The FPGA supports four targets')
    out=[]
    for i,t in enumerate(payload['targets']):
        if not isinstance(t,dict):raise ValueError('Invalid target')
        values=[t.get('delay_us'),t.get('doppler_hz'),t.get('gain_db')]
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in values):
            raise ValueError('Delay, Doppler and gain must be finite numbers')
        delay,doppler,gain=values
        if not 0<=delay<=2047/fs*1e6:raise ValueError('Delay exceeds FPGA buffer')
        if not -fs/2<doppler<fs/2:raise ValueError('Doppler must be inside the sample-rate Nyquist limits')
        if not -90<=gain<=0:raise ValueError('Gain must be between -90 and 0 dB')
        enabled=t.get('enabled',True)
        if not isinstance(enabled,bool):raise ValueError('enabled must be boolean')
        samples=round(delay*fs/1e6)
        step=round(doppler/fs*2**32)
        g=min(32767,round(32768*10**(gain/20)))
        out.append(dict(id=i+1,enabled=enabled,delay_us=samples/fs*1e6,delay_samples=samples,
                        doppler_hz=step*fs/2**32,phase_increment=step,gain_db=gain,gain_q15=g))
    return out

class Controller:
    def __init__(self,args):
        self.args=args;self.lock=threading.Lock();self.targets=[];self.clipped=False
        self.error=None;self.connected=args.demo;self.revision=0
    def call(self,command,stdin=None):
        if self.args.demo:return None
        env=os.environ.copy()
        env['SSHPASS']=os.environ.get('PLUTO_PASSWORD','analog')
        cmd=['sshpass','-e','ssh','-o','ConnectTimeout=3','-o','StrictHostKeyChecking=accept-new',
             '-o',f'UserKnownHostsFile={ROOT}/build/known_hosts','-o','LogLevel=ERROR',
             f'root@{self.args.pluto}',f'if [ -f /tmp/radar-loaded ]; then /tmp/rtsctl {command}; else echo "Radar FPGA is not loaded; run scripts/deploy.sh" >&2; exit 1; fi']
        p=subprocess.run(cmd,input=stdin,text=True,capture_output=True,timeout=6,env=env)
        if p.returncode:raise RuntimeError(p.stderr.strip() or 'Pluto control failed')
        self.connected=True;self.error=None
        result=json.loads(p.stdout)
        if result.get('sample_rate_hz'):self.args.sample_rate=result['sample_rate_hz']
        return result
    def state(self):
        return dict(mode='demo' if self.args.demo else 'hardware',connected=self.connected,error=self.error,
                    pluto=self.args.pluto,espargos=None,sample_rate_hz=self.args.sample_rate,
                    frequency_hz=self.args.frequency,max_targets=4,max_delay_us=2047/self.args.sample_rate*1e6,
                    delay_step_us=1e6/self.args.sample_rate,doppler_step_hz=self.args.sample_rate/2**32,
                    targets=self.targets,clipped=self.clipped,revision=self.revision,
                    hardware_latency_us=.325 if self.args.demo else None,latency_calibrated=False)
    def refresh(self):
        result=self.call('status')
        if result:
            self.clipped=result['clipped']
            self.targets=[]
            for i,t in enumerate(result['targets']):
                if not t['gain_q15'] and not result['mask']&(1<<i):continue
                self.targets.append(dict(id=i+1,enabled=bool(result['mask']&(1<<i)),
                    delay_us=t['delay_samples']/self.args.sample_rate*1e6,
                    doppler_hz=t['phase_increment']*self.args.sample_rate/2**32,
                    gain_db=max(-90,20*math.log10(max(t['gain_q15'],1)/32768)),**t))
        return self.state()
    def apply(self,payload):
        if not self.args.demo:self.call('status')
        targets=validate(payload,self.args.sample_rate)
        mask=sum(1<<i for i,t in enumerate(targets) if t['enabled'])
        lines=[str(mask)]+[f"{t['delay_samples']} {t['phase_increment']&0xffffffff} {t['gain_q15']}" for t in targets]
        lines+=['0 0 0']*(4-len(targets))
        result=self.call('apply','\n'.join(lines)+'\n')
        self.targets=targets;self.clipped=bool(result and result['clipped']);self.revision+=1
        return self.state()
    def mute(self):
        self.call('mute')
        for t in self.targets:t['enabled']=False
        self.revision+=1
        return self.state()

class Handler(BaseHTTPRequestHandler):
    def send_json(self,value,status=200):
        data=json.dumps(value,allow_nan=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_GET(self):
        if self.path=='/api/state':
            with self.server.controller.lock:
                try:self.send_json(self.server.controller.refresh())
                except (RuntimeError,subprocess.TimeoutExpired,ValueError,OSError) as e:
                    self.server.controller.connected=False;self.server.controller.error=str(e)
                    self.send_json(self.server.controller.state())
            return
        names={'/':'index.html','/app.js':'app.js','/style.css':'style.css','/logo.svg':'logo.svg','/config.js':'config.js','/favicon.ico':'favicon.ico','/fonts.css':'fonts.css'}
        if self.path not in names:self.send_error(404);return
        path=ROOT/'web'/names[self.path];data=path.read_bytes()
        self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(path)[0] or 'text/plain')
        self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_POST(self):
        # Reject cross-origin browser writes to the local hardware controller.
        origin=self.headers.get('Origin')
        if origin and origin!='http://'+self.headers.get('Host',''):
            self.send_json({'error':'Cross-origin request rejected'},403);return
        if self.path not in ('/api/apply','/api/mute'):self.send_error(404);return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<0 or length>16384:raise ValueError('Invalid request size')
            payload=json.loads(self.rfile.read(length) or '{}')
            with self.server.controller.lock:
                if self.path=='/api/apply':result=self.server.controller.apply(payload)
                else:result=self.server.controller.mute()
            self.send_json(result)
        except (ValueError,TypeError) as e:self.send_json({'error':str(e)},400)
        except (RuntimeError,subprocess.TimeoutExpired,OSError) as e:self.send_json({'error':str(e)},503)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--demo',action='store_true',help='UI preview without hardware writes')
    p.add_argument('--pluto',default='192.168.4.1');p.add_argument('--bind',default='127.0.0.1')
    p.add_argument('--port',type=int,default=8080);p.add_argument('--sample-rate',type=float,default=20e6)
    p.add_argument('--frequency',type=float,default=2380e6)
    args=p.parse_args()
    if not math.isfinite(args.sample_rate) or args.sample_rate<=0:p.error('Invalid sample rate')
    (ROOT/'build').mkdir(exist_ok=True)
    server=ThreadingHTTPServer((args.bind,args.port),Handler);server.controller=Controller(args)
    print(f"Target Studio: http://{args.bind}:{args.port} ({'DEMO' if args.demo else 'HARDWARE'})",flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        if not args.demo:
            try:server.controller.mute()
            except Exception as e:print(f'Could not mute on shutdown: {e}',flush=True)
        server.server_close()
if __name__=='__main__':main()
