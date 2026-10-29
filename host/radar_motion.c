#define _POSIX_C_SOURCE 200809L
#include "radar_motion.h"
#include <fcntl.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

radar_motion *radar_motion_open(bool create) {
    int fd = open(RADAR_MOTION_FILE, O_RDWR | (create ? O_CREAT : 0), 0600);
    if (fd < 0)
        return NULL;
    struct stat st;
    if ((create && ftruncate(fd, sizeof(radar_motion))) || fstat(fd, &st) ||
        st.st_size != sizeof(radar_motion)) {
        close(fd);
        return NULL;
    }
    void *p = mmap(NULL, sizeof(radar_motion), PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    close(fd);
    if (p == MAP_FAILED)
        return NULL;
    if (!create && ((radar_motion *)p)->magic != RADAR_MOTION_MAGIC) {
        munmap(p, sizeof(radar_motion));
        return NULL;
    }
    return p;
}
void radar_motion_close(radar_motion *motion) {
    if (motion)
        munmap(motion, sizeof(*motion));
}
double radar_motion_now(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}
bool radar_motion_available(const radar_motion *motion) {
    return motion && motion->magic == RADAR_MOTION_MAGIC &&
           radar_motion_now() - motion->heartbeat < 2;
}

/* Positive displayed radial velocity means receding: v = -fd*c/(2*fc).
 * Keep fractional delay between commits; only the FPGA delay word is rounded.
 * A triangular trajectory handles arbitrarily many reflections in one tick. */
void radar_motion_advance(radar_motion *m, radar_scene *scene, double now, double rate,
                          double carrier) {
    double elapsed = fmax(0, now - m->updated);
    m->updated = now;
    for (unsigned i = 0; i < RADAR_TARGETS; ++i) {
        radar_target *t = &scene->targets[i];
        if (t->delay != m->last.targets[i].delay || t->phase != m->last.targets[i].phase)
            m->position[i] = t->delay;
        if (!(m->mask & scene->mask & (1u << i)) || !(m->upper >= 1) || !(rate > 0) ||
            !(carrier > 0))
            continue;
        double speed = -(int32_t)t->phase * rate / 4294967296.0 * rate / carrier;
        double position = fmin(m->upper, fmax(0, m->position[i]));
        double unfolded = speed >= 0 ? position : 2 * m->upper - position;
        double folded = fmod(unfolded + fabs(speed) * elapsed, 2 * m->upper);
        bool returning = folded >= m->upper;
        m->position[i] = returning ? 2 * m->upper - folded : folded;
        uint32_t magnitude = (uint32_t)llabs((long long)(int32_t)t->phase);
        t->phase = returning ? magnitude : 0u - magnitude;
        t->delay = (uint32_t)llround(m->position[i]);
    }
    m->last = *scene;
}

void radar_motion_configure(radar_motion *m, radar_scene *scene, uint32_t mask,
                            uint32_t position_edits, uint32_t phase_edits, double upper,
                            double now) {
    for (unsigned i = 0; i < RADAR_TARGETS; ++i) {
        uint32_t bit = 1u << i;
        bool was_moving = (m->mask & bit) != 0;
        if (was_moving && !(position_edits & bit))
            scene->targets[i].delay = m->last.targets[i].delay;
        else
            m->position[i] = scene->targets[i].delay;
        if (was_moving && !(phase_edits & bit))
            scene->targets[i].phase = m->last.targets[i].phase;
        if ((mask & bit) && m->position[i] > upper) {
            m->position[i] = upper;
            scene->targets[i].delay = (uint32_t)llround(upper);
            scene->targets[i].phase = (uint32_t)llabs((long long)(int32_t)scene->targets[i].phase);
        }
    }
    m->mask = mask;
    m->upper = upper;
    m->last = *scene;
    m->updated = now;
}
