#include "radar_latency.h"
#include <assert.h>
#include <stdio.h>

int main(void) {
    /* Every UI bandwidth must have a usable range origin in either mode. */
    for (int standard = 0; standard <= 1; ++standard) {
        uint32_t version = standard ? 0x00020003 : 0x00020002;
        unsigned long rate = standard ? 61440000 : 160000000;
        double previous = radar_bandwidth_latency(version, rate, 200000);
        for (unsigned bandwidth = 200000; bandwidth <= 56000000; bandwidth += 10000) {
            double delay = radar_bandwidth_latency(version, rate, bandwidth);
            assert(isfinite(delay) && delay > .3 && delay < 5);
            assert(fabs(delay - previous) < .1);
            previous = delay;
        }
        assert(isnan(radar_bandwidth_latency(version, rate, 199999)));
        assert(isnan(radar_bandwidth_latency(version, rate, 56000001)));
        assert(isnan(radar_bandwidth_latency(version, rate, NAN)));
        assert(isnan(radar_bandwidth_latency(version, rate, INFINITY)));
    }
    assert(isnan(radar_bandwidth_latency(0x00020003, 160000000, 20000000)));
    assert(isnan(radar_bandwidth_latency(0x00020002, 61440000, 20000000)));
    assert(isnan(radar_bandwidth_latency(0x00010010, 160000000, 20000000)));
    puts("PASS: continuous bandwidth-dependent latency, mode selection and unsupported settings");
}
