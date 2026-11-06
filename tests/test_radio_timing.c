#include "radio_timing.h"
#include <assert.h>
#include <stdio.h>

int main(void) {
    radio_timing_window window;
    assert(radio_timing_pick(0, -1, &window) == -1 && window.width == 0);
    assert(radio_timing_pick(UINT32_MAX, -1, &window) == 15 && window.width == 32);
    uint32_t eye = (1u << 13) | (1u << 14);
    assert(radio_timing_pick(eye, -1, &window) == 13);
    /* If the center fails the long test, actually try its passing neighbor. */
    assert(radio_timing_pick(eye, 14, &window) == 14);
    assert(radio_timing_pick(eye, 15, &window) == -1);
    assert(radio_timing_pick(eye, 32, &window) == -1);
    assert(radio_timing_pick(0xe0000003u, -1, &window) == 30);
    assert(window.start == 29 && window.width == 3);
    for (int tap = 0; tap < 32; ++tap) {
        assert(radio_timing_pick(1u << tap, tap, &window) == tap);
        assert(radio_timing_pick(1u << tap, -1, &window) == tap);
    }
    puts("PASS: timing-eye centers, edge taps and explicit retry selection");
}
