#!/usr/bin/env bash
# Volatile, explicitly experimental 122.88 MHz activation. Reboot restores flash.
set -euo pipefail
printf "%s\n" "Refusing to load the initial fast image: sustained signal-integrity checks rejected it. Use a separately qualified experiment image." >&2
exit 1
cd "$(dirname "$0")/.."
export SSHPASS="${PLUTO_PASSWORD:-analog}"
ssh_opts=(-F /dev/null -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$PWD/build/known_hosts" -o ConnectTimeout=5)
# Check the exact archived fast bitstream, not the normal firmware build.
python3 - <<'PY'
import hashlib,json
from pathlib import Path
p=Path('build/latency-round3/fast-interface')
m=json.loads((p/'manifest.json').read_text())
assert m['intended_sample_rate_hz']==122880000
assert hashlib.sha256((p/'radar.bit').read_bytes()).hexdigest()==m['sha256']['radar.bit']
assert 'All user specified timing constraints are met.' in (p/'timing.log').read_text()
PY
python3 scripts/bit_to_bin.py build/latency-round3/fast-interface/radar.bit build/latency-round3/fast-interface/radar.bin
sshpass -e scp -O "${ssh_opts[@]}" build/latency-round3/fast-interface/radar.bin build/rtsctl scripts/radio_setup.sh scripts/load_on_pluto.sh root@192.168.4.1:/tmp/
sshpass -e ssh "${ssh_opts[@]}" root@192.168.4.1 'sh /tmp/load_on_pluto.sh'
python3 scripts/experimental_fast_clock.py --fast-fpga-loaded --output build/fast-live-profile.json
sshpass -e ssh "${ssh_opts[@]}" root@192.168.4.1 'echo "0 1" > /sys/kernel/debug/iio/iio:device0/digital_tune'
# The driver's tune command can return success even after a failed eye scan.
# Independently require locked RX and TX-loopback PN checkers without errors.
python3 scripts/check_radio_pn.py --output build/fast-live-pn.json
printf 'Experimental 122.88 MSa/s profile active; targets muted, TX attenuation 60 dB. Reboot restores installed firmware.\n'
