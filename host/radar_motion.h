#ifndef RADAR_MOTION_H
#define RADAR_MOTION_H
#include "radar_control.h"
#ifndef RADAR_MOTION_FILE
#define RADAR_MOTION_FILE "/tmp/radar-motion.state"
#endif
#define RADAR_MOTION_MAGIC 0x4d4f5431u

typedef struct {
    uint32_t magic, mask;
    double upper, updated, heartbeat;
    double position[RADAR_TARGETS];
    radar_scene last;
} radar_motion;

/* All access to this shared state is protected by the hardware control lock. */
radar_motion *radar_motion_open(bool create);
void radar_motion_close(radar_motion *motion);
double radar_motion_now(void);
bool radar_motion_available(const radar_motion *motion);
void radar_motion_advance(radar_motion *motion, radar_scene *scene, double now, double rate,
                          double carrier);
void radar_motion_configure(radar_motion *motion, radar_scene *scene, uint32_t mask,
                            uint32_t position_edits, uint32_t phase_edits, double upper,
                            double now);
#endif
