#ifndef RADAR_LATENCY_H
#define RADAR_LATENCY_H

#include <math.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdint.h>

/* Reference RF delays, including fractional interpolation. These are not a
 * per-device calibration. Interpolation uses inverse bandwidth because analog
 * filter delay changes most rapidly at the narrow end of the tuning range.
 * Measurement procedure: espargos-experiments/scripts/bandwidth_latency.py. */
static inline double radar_bandwidth_latency(uint32_t version, unsigned long rate,
                                            double bandwidth_hz) {
    static const struct {
        double mhz, standard_us, overclocked_us;
    } reference[] = {
        {0.2, 2.9914811, 2.0068677},
        {0.3, 3.0125668, 2.0948480},
        {0.4, 3.0003295, 2.0867317},
        {0.5, 2.7459654, 1.8504725},
        {0.75, 2.4611795, 1.5551841},
        {1, 2.2834142, 1.3620940},
        {1.5, 2.0109526, 1.1057239},
        {2, 1.8322042, 0.9237241},
        {3, 1.6436274, 0.7392000},
        {5, 1.5105041, 0.6097013},
        {8, 1.4291107, 0.5276192},
        {12, 1.3839932, 0.4792474},
        {16, 1.3628846, 0.4606458},
        {20, 1.3500000, 0.4500000},
        {25, 1.3394852, 0.4363165},
        {30, 1.3323579, 0.4258591},
        {40, 1.3213814, 0.4197869},
        {50, 1.3216404, 0.4169090},
        {56, 1.3187500, 0.4140625},
    };
    bool standard = version == 0x00020003 && rate == 61440000;
    bool overclocked = version == 0x00020002 && rate == 160000000;
    if ((!standard && !overclocked) || !isfinite(bandwidth_hz) ||
        bandwidth_hz < reference[0].mhz * 1e6 || bandwidth_hz > 56e6)
        return NAN;
    double bandwidth = bandwidth_hz / 1e6;
    for (size_t i = 1; i < sizeof(reference) / sizeof(reference[0]); ++i) {
        if (bandwidth > reference[i].mhz)
            continue;
        double lower = standard ? reference[i-1].standard_us : reference[i-1].overclocked_us;
        double upper = standard ? reference[i].standard_us : reference[i].overclocked_us;
        double weight = (1 / bandwidth - 1 / reference[i-1].mhz) /
                        (1 / reference[i].mhz - 1 / reference[i-1].mhz);
        return lower + weight * (upper - lower);
    }
    return NAN;
}

#endif
