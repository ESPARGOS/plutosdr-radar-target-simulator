#!/usr/bin/env bash
# Load only volatile FPGA RAM; a Pluto reboot restores its installed image.
set -euo pipefail
cd "$(dirname "$0")/.."
pluto_host="${1:-192.168.4.1}"
export SSHPASS="${PLUTO_PASSWORD:-analog}"
ssh_opts=(-o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$PWD/build/known_hosts" -o ConnectTimeout=5 -o ServerAliveInterval=5 -o ServerAliveCountMax=3)
python3 scripts/check_build.py
python3 scripts/build_tools.py --check
python3 scripts/bit_to_bin.py vendor/adi-hdl/projects/pluto/pluto.runs/impl_1/system_top.bit build/radar.bin
sshpass -e scp -O "${ssh_opts[@]}" build/radar.bin build/rtsctl build/radio-pn scripts/radio_setup.sh scripts/radio_fast_setup.sh scripts/load_on_pluto.sh "root@$pluto_host:/tmp/"
sshpass -e ssh "${ssh_opts[@]}" "root@$pluto_host" 'sh /tmp/load_on_pluto.sh'
