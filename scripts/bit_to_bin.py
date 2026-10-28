#!/usr/bin/env python3
"""Extract a Xilinx .bit payload and byte-swap words for the Zynq FPGA manager."""
import argparse,struct
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('bit');p.add_argument('bin');a=p.parse_args()
b=Path(a.bit).read_bytes();pos=0
n=struct.unpack_from('>H',b,pos)[0];pos+=2+n
n=struct.unpack_from('>H',b,pos)[0];pos+=2
if n!=1:raise ValueError('Invalid .bit header')
while pos<len(b):
 key=b[pos:pos+1];pos+=1
 if key==b'e':
  n=struct.unpack_from('>I',b,pos)[0];pos+=4
  data=b[pos:pos+n]
  if len(data)!=n or n%4:raise ValueError('Invalid bitstream payload length')
  if b'\xaa\x99\x55\x66' not in data:raise ValueError('Missing FPGA synchronization word')
  Path(a.bin).write_bytes(b''.join(data[i:i+4][::-1] for i in range(0,n,4)))
  print(f'Wrote {n} bytes to {a.bin}');break
 n=struct.unpack_from('>H',b,pos)[0];pos+=2+n
else:raise ValueError('Missing bitstream payload')
