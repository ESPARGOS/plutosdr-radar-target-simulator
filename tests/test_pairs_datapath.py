#!/usr/bin/env python3
"""Bit-exact oracle: random IQ, signed Doppler, independent delays, wrap, clipping,
configuration changes, phase continuity, startup and sample-clock gaps."""
import math, random, subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
build=root/'build/tests';build.mkdir(parents=True,exist_ok=True)
rng=random.Random(42)
rows=[]
for c in range(15000):
    reset=int(c<3 or 6500<=c<6503)
    configure=int(c in (3,3101,3501,6001,6503,9401,11001,12501))
    restart=int(c in (3,6503,11001))
    valid=int((c%2==0 or 5000<c<5800 or c in (3501,6001,9401,12501)) and c not in (6002,6504))
    ds=[0,1,17,2047] if c<3101 else [3,9,100,1025]
    if c>=9401: ds=[0,0,0,0]
    inc=[0,2**28,(-2**27)&0xffffffff,0xffffffff]
    if c>=6001: inc=[(-2**29)&0xffffffff,0,98765,2**28]
    mask=15 if c<11001 or c>=12501 else 0
    gain=[8192,12000,16384,4000] if c<9401 else [32767]*4
    iq=[rng.randrange(-32768,32768),rng.randrange(-32768,32768)]
    rows.append([reset,configure,restart,valid,*iq,mask,*ds,*inc,*gain])
with (build/'stimulus.txt').open('w') as f:
    for row in rows:f.write(' '.join(map(str,row))+'\n')
subprocess.run(['iverilog','-g2012','-s','tb','-o',str(build/'tb'),str(root/'experiments/fast-interface/target_bank_pairs.sv'),str(root/'rtl/nco_rom.v'),str(root/'tests/tb_bank.sv')],check=True)
subprocess.run(['vvp',str(build/'tb')],cwd=build,check=True)
actual=[list(map(int,x.split())) for x in (build/'output.txt').read_text().splitlines()]
assert len(actual)==len(rows),(len(actual),len(rows))
history=[];phases=[0]*4;pending={};held=(0,0);clipped=0;checks=0
ready_at=10**9;commit_at=None;active=(0,[0]*4,[0]*4,[0]*4);clip_pending=0
for c,(row,out) in enumerate(zip(rows,actual)):
    reset,configure,restart,valid,ii,qq,mask,*params=row
    if reset:
        history=[];phases=[0]*4;pending={};held=(0,0);clipped=0;ov=0
        ready_at=10**9;commit_at=None;active=(0,[0]*4,[0]*4,[0]*4);clip_pending=0
    else:
        clipped|=clip_pending;clip_pending=0
        ov=int(c in pending)
        if ov:
            value=pending.pop(c);clip_pending=int(any(x< -32768 or x>32767 for x in value))
            held=tuple(max(-32768,min(32767,x)) for x in value)
        if valid:
            enabled,ds,incs,gains=active;sums=[0,0]
            for t in range(4):
                x,y=(ii,qq) if ds[t]==0 else (history[-ds[t]] if len(history)>=ds[t] else (0,0))
                if not enabled&(1<<t):x=y=0
                angle=(phases[t]>>22)*2*math.pi/1024
                co=(round(32767*math.cos(angle))*gains[t])>>15
                si=(round(32767*math.sin(angle))*gains[t])>>15
                sums[0]+=(x*co-y*si)>>15;sums[1]+=(x*si+y*co)>>15
                phases[t]=(phases[t]+incs[t])&0xffffffff
            if c>=ready_at:pending[c+3]=sums
            history.append((ii,qq))
        flush=False
        if configure:
            requested=(mask,params[:4],params[4:8],params[8:])
            if mask:
                commit_at=c+1027;next_active=requested;next_restart=restart
            else:
                commit_at=None;active=requested;ready_at=10**9;flush=True
                if restart:phases=[0]*4
        elif commit_at==c:
            active=next_active;ready_at=c+2;commit_at=None;flush=True
            if next_restart:phases=[0]*4
        if flush:
            pending={};held=(0,0);clipped=0;clip_pending=0;ov=0
    expected=[ov,*held,clipped]
    assert out==expected,f'cycle {c}: actual {out}, expected {expected}'
    checks+=ov
print(f'PASS: {len(rows)} clocks, {checks} IQ outputs; old scene remains active during table reload; immediate mute; atomic handoff')
