#!/usr/bin/env python3
"""Assemble radar firmware using an existing Pluto image.
Keep the kernel and root filesystem metadata, replace the FPGA, disable Maia
services that use it, and add the radar startup script.
"""
import gzip,hashlib,os,shutil,struct,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/firmware';BASE=OUT/'original.itb'
subprocess.run(['python3',str(ROOT/'scripts/check_build.py')],check=True)
assert BASE.exists(),'Back up and extract original.itb first'
for i,name in enumerate(['rev-a.dtb','rev-b.dtb','rev-c.dtb','original.bit','zImage','original-rootfs.cpio.gz']):
 subprocess.run(['dumpimage','-T','flat_dt','-p',str(i),'-o',str(OUT/name),str(BASE)],check=True,stdout=subprocess.DEVNULL)
for name in ['rev-a.dtb','rev-b.dtb','rev-c.dtb']:
 for node in ['/fpga-axi@0/maia-sdr@7C400000','/maia-sdr-recording','/maia-sdr-spectrometer']:
  subprocess.run(['fdtput','-t','s',str(OUT/name),node,'status','disabled'],check=True)
# Preserve every original newc record byte-for-byte unless explicitly replaced.
data=gzip.decompress((OUT/'original-rootfs.cpio.gz').read_bytes());pos=0;records={}
while pos<len(data):
 start=pos;header=data[pos:pos+110];assert header[:6] in (b'070701',b'070702')
 fields=[int(header[6+8*i:14+8*i],16) for i in range(13)];size=fields[6];namesize=fields[11]
 pos+=110;name=data[pos:pos+namesize-1].decode();pos=(pos+namesize+3)&~3
 payload=data[pos:pos+size];pos=(pos+size+3)&~3
 if name=='TRAILER!!!':break
 records[name]=(data[start:pos],payload)
def new_record(name,payload,mode=0o100755):
 n=name.encode()+b'\0'
 fields=[0,mode,0,0,1,0,len(payload),0,0,0,0,len(n),0]
 b=b'070701'+b''.join(f'{v:08x}'.encode() for v in fields)+n
 b+=b'\0'*(-len(b)%4);b+=payload;b+=b'\0'*(-len(payload)%4)
 return b
for name in ['etc/init.d/S50maia-kmod','etc/init.d/S60maia-httpd']:
 records.pop(name,None);records.pop('./'+name,None)
startup=(ROOT/'host/S61radar').read_bytes()
additions={'usr/bin/rtsctl':(ROOT/'build/rtsctl').read_bytes(),
 'usr/bin/radar-radio-setup':(ROOT/'scripts/radio_setup.sh').read_bytes(),
 'usr/bin/radar-radio-fast':(ROOT/'scripts/radio_fast_setup.sh').read_bytes(),
 'usr/bin/radio-pn':(ROOT/'build/radio-pn').read_bytes(),
 'etc/init.d/S61radar':startup}
additions['usr/bin/radar.cgi']=(ROOT/'build/radar.cgi').read_bytes()
records['usr/share/radar-web']=(new_record('usr/share/radar-web',b'',0o40755),b'')
for asset in (ROOT/'web').iterdir():
 if asset.is_file():
  payload=asset.read_bytes() if asset.name!='config.js' else b'window.RADAR_DEVICE = true;\n'
  name='usr/share/radar-web/'+asset.name
  records[name]=(new_record(name,payload,0o100644),payload)
for name,payload in additions.items():
 records.pop('./'+name,None);records[name]=(new_record(name,payload),payload)
archive=b''.join(r[0] for r in records.values())+new_record('TRAILER!!!',b'',0)
archive+=b'\0'*(-len(archive)%512)
(OUT/'rootfs.cpio.gz').write_bytes(gzip.compress(archive,mtime=0))
shutil.copyfile(ROOT/'vendor/adi-hdl/projects/pluto/pluto.runs/impl_1/system_top.bit',OUT/'radar.bit')
# Pluto U-Boot patches the embedded DTB before bootm (adi_loadvals).
# Match the stock FIT: DTBs must not have hashes invalidated by those patches.
images=[]
for num,name in enumerate(['rev-a.dtb','rev-b.dtb','rev-c.dtb'],1):
 images.append(f'fdt@{num} {{ description="Radar {name}"; data=/incbin/("{name}"); type="flat_dt"; arch="arm"; compression="none"; }};')
images+=['''fpga@1 { description="Four-target radar FPGA"; data=/incbin/("radar.bit"); type="fpga"; arch="arm"; compression="none"; load=<0x0f000000>; hash@1 { algo="md5"; }; };''',
'''linux_kernel@1 { description="Original Pluto kernel"; data=/incbin/("zImage"); type="kernel"; arch="arm"; os="linux"; compression="none"; load=<0x8000>; entry=<0x8000>; hash@1 { algo="md5"; }; };''',
'''ramdisk@1 { description="Radar rootfs"; data=/incbin/("rootfs.cpio.gz"); type="ramdisk"; arch="arm"; os="linux"; compression="gzip"; hash@1 { algo="md5"; }; };''']
configs=[]
for i in range(11):
 fdt=1 if i==0 else 3 if i==8 else 2
 configs.append(f'config@{i} {{ description="Pluto radar target simulator"; fdt="fdt@{fdt}"; kernel="linux_kernel@1"; ramdisk="ramdisk@1"; fpga="fpga@1"; }};')
its='/dts-v1/;\n/ { description="Pluto FPGA radar target simulator"; magic="ITB PlutoSDR (ADALM-PLUTO)"; #address-cells=<1>; images {\n'+'\n'.join(images)+'\n}; configurations { default="config@0";\n'+'\n'.join(configs)+'\n}; };\n'
(OUT/'radar.its').write_text(its)
subprocess.run(['mkimage','-f','radar.its','radar.itb'],cwd=OUT,check=True,stdout=subprocess.DEVNULL)
fit=(OUT/'radar.itb').read_bytes();frm=fit+hashlib.md5(fit).hexdigest().encode()+b'\n'
assert len(frm)<0x1e00000
(OUT/'pluto.frm').write_bytes(frm)
(OUT/'pluto.frm.sha256').write_text(hashlib.sha256(frm).hexdigest()+'  pluto.frm\n')
print(f'Built {OUT / "pluto.frm"} ({len(frm)} bytes) from original device firmware')
