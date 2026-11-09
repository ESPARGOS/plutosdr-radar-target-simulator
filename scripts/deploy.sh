#!/usr/bin/env bash
# Load the FPGA, control tools and web interface into volatile storage.
# A Pluto reboot restores its installed image.
set -euo pipefail
cd "$(dirname "$0")/.."
pluto_host="${1:-192.168.2.1}"
export SSHPASS="${PLUTO_PASSWORD:-analog}"
ssh_opts=(-o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$PWD/build/known_hosts" -o ConnectTimeout=5 -o ServerAliveInterval=5 -o ServerAliveCountMax=3)
python3 scripts/check_build.py
python3 scripts/build_tools.py --check
python3 scripts/bit_to_bin.py vendor/adi-hdl/projects/pluto/pluto.runs/impl_1/system_top.bit build/radar.bin
python3 scripts/bit_to_bin.py build/standard-hdl/projects/pluto/pluto.runs/impl_1/system_top.bit build/radar-standard.bin
python3 - <<'PY'
import io, tarfile
from pathlib import Path
with tarfile.open('build/radar-web.tar', 'w') as archive:
    for asset in sorted(Path('web').iterdir()):
        if not asset.is_file():
            continue
        payload = b'window.RADAR_DEVICE = true;\n' if asset.name == 'config.js' else asset.read_bytes()
        entry = tarfile.TarInfo(asset.name)
        entry.size, entry.mode = len(payload), 0o644
        archive.addfile(entry, io.BytesIO(payload))
PY
sshpass -e scp -O "${ssh_opts[@]}" build/radar.bin build/radar-standard.bin build/rtsctl build/radio-pn build/radar.cgi build/radar-web.tar scripts/radio_setup.sh scripts/radio_fast_setup.sh scripts/load_on_pluto.sh scripts/load_profile.sh host/S61radar "root@$pluto_host:/tmp/"
sshpass -e ssh "${ssh_opts[@]}" "root@$pluto_host" 'sh /tmp/load_on_pluto.sh'
