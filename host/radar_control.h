#ifndef RADAR_CONTROL_H
#define RADAR_CONTROL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define RADAR_INVALID -2
#define RADAR_TARGETS 4
#define RADAR_MAX_DELAY 16383
#define RADAR_MAX_GAIN 32767
#define RADAR_SIGNATURE 0x52545331u
#define RADAR_BASE 0x43c00000u
#define RADAR_MAP_SIZE 4096

enum radar_register {
    RADAR_REG_SIGNATURE = 0,
    RADAR_REG_VERSION = 1,
    RADAR_REG_MAX_DELAY = 3,
    RADAR_REG_COMMIT = 4,
    RADAR_REG_STATUS = 5,
    RADAR_REG_CLIPPED = 6,
    RADAR_REG_ENABLE = 8,
    RADAR_REG_FRACTION_BITS = 10,
    RADAR_REG_TARGET_BASE = 16,
    RADAR_REG_STEP_BASE = 32,
    RADAR_REG_MOTION = 40,
    RADAR_REG_UPPER = 41,
    RADAR_REG_SNAPSHOT = 64
};

typedef struct {
    uint32_t delay;
    uint32_t phase;
    uint32_t gain;
    uint32_t fraction; /* Fractional sample in unsigned Q0.16. */
} radar_target;

typedef struct {
    uint32_t mask;
    radar_target targets[RADAR_TARGETS];
} radar_scene;

/* Linux and test backends implement the same small I/O boundary. */
typedef struct {
    uint32_t (*read_register)(void *context, unsigned index);
    void (*write_register)(void *context, unsigned index, uint32_t value);
    int (*read_attribute)(void *context, const char *name, char *value, size_t size);
    int (*write_attribute)(void *context, const char *name, const char *value);
    void (*sleep_ms)(void *context, unsigned milliseconds);
} radar_io;

typedef struct {
    const radar_io *io;
    void *context;
    const char *error;
} radar_device;

typedef struct {
    double minimum, step, maximum;
} radar_gain_limits;

int radar_check(radar_device *device);
int radar_wait_idle(radar_device *device);
int radar_commit(radar_device *device);
int radar_parse_scene(const char *text, radar_scene *scene);
int radar_apply(radar_device *device, const radar_scene *scene);
bool radar_fpga_motion(radar_device *device);
unsigned radar_max_delay(radar_device *device);
int radar_snapshot(radar_device *device);
int radar_apply_motion(radar_device *device, const radar_scene *scene, unsigned moving,
                       unsigned position_edits, unsigned velocity_edits, unsigned upper);
int radar_mute(radar_device *device);
void radar_get_scene(radar_device *device, radar_scene *scene);
unsigned long radar_sample_rate(radar_device *device);
int radar_read_number(radar_device *device, const char *attribute, double *value);
int radar_get_gain_limits(radar_device *device, bool tx, radar_gain_limits *limits);
int radar_set_gain(radar_device *device, bool tx, double gain);
void radar_carrier_limits(radar_device *device, uint64_t *minimum, uint64_t *maximum);
bool radar_wide_bandwidth_available(radar_device *device);
unsigned radar_max_bandwidth(radar_device *device);
int radar_set_bandwidth(radar_device *device, unsigned hz);
int radar_set_carrier(radar_device *device, uint64_t hz);

#endif
