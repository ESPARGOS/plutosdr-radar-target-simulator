#ifndef FAKE_DEVICE_H
#define FAKE_DEVICE_H
#include "radar_control.h"

typedef struct {
    uint32_t registers[64];
    unsigned register_writes, attribute_reads, attribute_writes, sleeps;
    bool stuck, missing_radio, fail_rollback;
    unsigned fail_write_at, ignore_write_at;
    const char *fail_read;
    char values[12][80];
} fake_device;
void fake_init(fake_device *fake, radar_device *device);
const char *fake_value(fake_device *fake, const char *name);
#endif
