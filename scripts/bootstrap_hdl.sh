#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
revision=065c8f186ef87ff049d279ed5859ee8d97d91808
[ ! -d vendor/adi-hdl ] || exit 0
mkdir -p vendor
scratch="${RTS_SCRATCH_DIR:-$PWD/build/scratch}"
mkdir -p "$scratch"
checkout=$(mktemp -d "$scratch/hdl.XXXXXXXX")
trap 'rm -rf "$checkout"' EXIT
if [ -n "${ADI_HDL_SOURCE:-}" ]; then
 git -C "$ADI_HDL_SOURCE" archive "$revision" -o "$checkout/hdl.tar"
else
 git -C "$checkout" init -q
 git -C "$checkout" fetch --depth 1 https://github.com/analogdevicesinc/hdl "$revision"
 git -C "$checkout" archive FETCH_HEAD -o "$checkout/hdl.tar"
fi
mkdir vendor/adi-hdl
tar -xf "$checkout/hdl.tar" -C vendor/adi-hdl
