#!/usr/bin/env python3
"""Reversible AD9363 filter experiments; NOT a production boot configuration.

The driver accepts explicit clock chains through a FIR configuration. After
calibrating that chain, bypass the unity FIR at its documented register bits.
Its cached FIR enable attribute remains 1: record both cache and real registers.
Restore with --profile stock (or reboot); never change rates during a capture.
All profiles retain the 61.44 MSa/s interface clock and rated converter clocks.
"""
import argparse
import json
import re
from pathlib import Path

import adi

FS = 61440000
# ADC/DAC, HB3 output, HB2 output, HB1 output (multiples of FS).
CHAINS = {
    'rx-no-hb1': ((4, 2, 1, 1), (4, 2, 1, 1)),
    'hb3-only': ((2, 1, 1, 1), (2, 1, 1, 1)),
    'hb2-only': ((2, 2, 1, 1), (2, 2, 1, 1)),
    'hb1-only': ((2, 2, 2, 1), (2, 2, 2, 1)),
    'no-hb': ((1, 1, 1, 1), (1, 1, 1, 1)),
}


def configure(profile, bandwidth=20000000, sample_rate=FS):
    FS = int(sample_rate)
    r = adi.Pluto('ip:192.168.4.1')
    r.tx_hardwaregain_chan0 = -60
    # Raw 122.88 MHz bypass exceeds the driver's rate validator. Restore its
    # original /2 stage before asking the driver to disable/reconfigure FIRs.
    current_rate = r._get_iio_attr('voltage0', 'sampling_frequency', False)
    if current_rate > 61440000 + 100:
        rxreg, txreg = r._ctrl.reg_read(3), r._ctrl.reg_read(2)
        adc = int(re.search(r'ADC:(\d+)', r._ctrl.attrs['rx_path_rates'].value)[1])
        if not 61440000 < current_rate < 122880100 or txreg & 31 != 16:
            raise RuntimeError('Unrecognized overclock profile; reboot to restore firmware')
        if abs(adc - 4 * current_rate) < 100 and rxreg & 31 == 24:
            rx_restore = 4
        elif abs(adc - 2 * current_rate) < 100 and rxreg & 31 == 16:
            rx_restore = 8
        else:
            raise RuntimeError('Unrecognized RX clock chain; reboot to restore firmware')
        r._ctrl.attrs['ensm_mode'].value = 'alert'
        try:
            r._ctrl.reg_write(3, rxreg | rx_restore)
            r._ctrl.reg_write(2, txreg | 8)
        finally:
            r._ctrl.attrs['ensm_mode'].value = 'fdd'
    r._set_iio_attr('out', 'voltage_filter_fir_en', False, 0)
    r._set_iio_attr('voltage0', 'sampling_frequency', False, FS)
    r.rx_rf_bandwidth = r.tx_rf_bandwidth = 20000000
    if profile != 'stock':
        rx, tx = CHAINS[profile]
        def rates(values):
            return ' '.join(map(str, (FS * 16, *(FS * x for x in values), FS)))
        fir = ('TX 3 GAIN 0 INT 1\nRX 3 GAIN 0 DEC 1\n'
               f'RTX {rates(tx)}\nRRX {rates(rx)}\n'
               f'BWRX {bandwidth}\nBWTX {bandwidth}\n32767,32767\n' + '0,0\n' * 15)
        r._ctrl.attrs['filter_fir_config'].value = fir
        r._set_iio_attr('out', 'voltage_filter_fir_en', False, 1)
        r._ctrl.attrs['ensm_mode'].value = 'alert'
        try:
            # REG_TX_ENABLE_FILTER_CTRL / REG_RX_ENABLE_FILTER_CTRL:
            # bits [1:0] = FIR enable and interpolation/decimation.
            # Unity-rate FIR bypass leaves the interface sample rate unchanged.
            for addr in (2, 3):
                r._ctrl.reg_write(addr, r._ctrl.reg_read(addr) & ~3)
        finally:
            r._ctrl.attrs['ensm_mode'].value = 'fdd'
    actual = {
        'profile': profile,
        'rx_path_rates': r._ctrl.attrs['rx_path_rates'].value,
        'tx_path_rates': r._ctrl.attrs['tx_path_rates'].value,
        'filter_control_registers': {str(a): r._ctrl.reg_read(a) for a in (2, 3)},
        'driver_fir_enabled': r._get_iio_attr('out', 'voltage_filter_fir_en', False),
        'sampling_frequency': r._get_iio_attr('voltage0', 'sampling_frequency', False),
        'rx_rf_bandwidth': r.rx_rf_bandwidth,
        'tx_rf_bandwidth': r.tx_rf_bandwidth,
    }
    assert abs(actual['sampling_frequency'] - FS) < 100
    assert all(v & 3 == 0 for v in actual['filter_control_registers'].values())
    return actual


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('stock', *CHAINS), required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--bandwidth', type=int, choices=(20000000, 40000000, 56000000), default=20000000,
                        help='Experimental analog bandwidth via FIR profile; >20 MHz is outside AD9363 specifications')
    args = parser.parse_args()
    text = json.dumps(configure(args.profile, args.bandwidth), indent=2) + '\n'
    if args.output:
        args.output.write_text(text)
    print(text, end='')
