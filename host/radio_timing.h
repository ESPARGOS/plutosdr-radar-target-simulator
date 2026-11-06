#ifndef RADIO_TIMING_H
#define RADIO_TIMING_H
#include <stdint.h>

typedef struct {
    unsigned start, width;
} radio_timing_window;

/* Pick the center on the first attempt. A retry must test the requested tap,
   rather than silently returning to a center that failed sustained checks. */
static inline int radio_timing_pick(uint32_t good, int preferred, radio_timing_window *window) {
    unsigned start = 0, width = 0;
    *window = (radio_timing_window){0};
    for (unsigned tap = 0; tap < 32; ++tap) {
        if (good & (1u << tap)) {
            if (!width)
                start = tap;
            if (++width > window->width)
                *window = (radio_timing_window){start, width};
        } else
            width = 0;
    }
    if (!window->width)
        return -1;
    if (preferred >= 0)
        return preferred < 32 && (good & (1u << preferred)) ? preferred : -1;
    return (int)(window->start + (window->width - 1) / 2);
}
#endif
