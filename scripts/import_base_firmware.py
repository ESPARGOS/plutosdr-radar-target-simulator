#!/usr/bin/env python3
"""Extract a FIT from a compatible Pluto FRM or raw qspi-linux backup.

This reads files only. It neither connects to nor flashes a device.
"""
import argparse
import hashlib
import struct
from pathlib import Path


def extract(data):
    if len(data) < 40 or data[:4] != b'\xd0\x0d\xfe\xed':
        raise ValueError('Input does not begin with a FIT/FDT header')
    size = struct.unpack_from('>I', data, 4)[0]
    if not 40 <= size <= len(data):
        raise ValueError('Truncated or invalid FIT size')
    fit = data[:size]
    if b'ITB PlutoSDR (ADALM-PLUTO)' not in fit:
        raise ValueError('Not a Pluto firmware FIT')
    if len(data) == size + 33:
        expected = hashlib.md5(fit).hexdigest().encode() + b'\n'
        if data[size:] != expected:
            raise ValueError('FRM checksum mismatch')
    return fit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, default=Path('build/firmware/original.itb'))
    args = parser.parse_args()
    try:
        fit = extract(args.input.read_bytes())
        if args.output.exists() and args.output.read_bytes() != fit:
            raise ValueError(f'Refusing to overwrite a different backup: {args.output}')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(fit)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'{exc}\n')
    print(f'{args.output}: {len(fit)} bytes, SHA256 {hashlib.sha256(fit).hexdigest()}')
    print('Header/checksum checked; verify base-firmware compatibility before packaging.')


if __name__ == '__main__':
    main()
