#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
scratch="${RTS_SCRATCH_DIR:-$PWD/build/scratch}"
mkdir -p "$scratch/container-tmp"
image="${RTS_BUILD_IMAGE:-ghcr.io/maia-sdr/maia-sdr-devel@sha256:a5cb1b566f18db4072cc2148cc46052241d9fd1eeae07ea1984aacd2552f9e85}"
xilinx="${RTS_XILINX_VOLUME:-vivado2023_2}"
exec docker run --rm --network host --user "$(id -u):$(id -g)" \
 --ulimit nofile=1024:1048576 \
 -v "$scratch:/scratch" -e TMPDIR=/scratch/container-tmp -e RTS_BUILD_IMAGE="$image" \
 -v "$xilinx:/opt/Xilinx:ro" -v "$PWD:/work" -w /work \
 --entrypoint /bin/bash "$image" \
 -c 'source /opt/Xilinx/Vivado/2023.2/settings64.sh; export PATH=/opt/oss-cad-suite/bin:$PATH; exec "$@"' bash "$@"
