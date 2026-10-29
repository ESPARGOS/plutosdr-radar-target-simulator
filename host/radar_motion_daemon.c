#define _DEFAULT_SOURCE
#include "radar_linux.h"
#include "radar_motion.h"
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/file.h>
#include <unistd.h>
static volatile sig_atomic_t stopped;
static void stop(int signal) {
    (void)signal;
    stopped = 1;
}
int main(void) {
    int singleton = open("/tmp/radar-motion.lock", O_CREAT | O_RDWR, 0600);
    if (singleton < 0 || flock(singleton, LOCK_EX | LOCK_NB))
        return 1;
    signal(SIGTERM, stop);
    signal(SIGINT, stop);
    radar_device device;
    radar_linux backend;
    if (radar_linux_open(&device, &backend))
        return 1;
    radar_motion *m = radar_motion_open(true);
    if (!m) {
        radar_linux_close(&backend);
        return 1;
    }
    *m = (radar_motion){.magic = RADAR_MOTION_MAGIC,
                        .upper = RADAR_MAX_DELAY,
                        .updated = radar_motion_now(),
                        .heartbeat = radar_motion_now()};
    radar_get_scene(&device, &m->last);
    for (unsigned i = 0; i < RADAR_TARGETS; ++i)
        m->position[i] = m->last.targets[i].delay;
    FILE *ready = fopen("/tmp/radar-motion.ready", "w");
    if (!ready) {
        radar_motion_close(m);
        radar_linux_close(&backend);
        return 1;
    }
    fclose(ready);
    flock(backend.lock_fd, LOCK_UN);
    int failed = 0;
    double next_tick = radar_motion_now();
    while (!stopped) {
        next_tick += .01;
        double remaining = next_tick - radar_motion_now();
        if (remaining > 0)
            usleep((useconds_t)(remaining * 1e6));
        else
            next_tick = radar_motion_now();
        if (flock(backend.lock_fd, LOCK_EX | LOCK_NB))
            continue;
        radar_scene before, after;
        radar_get_scene(&device, &before);
        after = before;
        double now = radar_motion_now(), carrier;
        unsigned long rate = radar_sample_rate(&device);
        if (rate != 160000000 ||
            radar_read_number(&device, "out_altvoltage0_RX_LO_frequency", &carrier)) {
            device.error = "Motion clock or carrier unavailable";
            failed = 1;
        } else {
            radar_motion_advance(m, &after, now, rate, carrier);
            if (memcmp(&before, &after, sizeof(before)))
                failed = radar_apply(&device, &after) != 0;
        }
        m->heartbeat = now;
        if (failed) {
            fprintf(stderr, "%s\n", device.error);
            radar_mute(&device);
            m->mask = 0;
            m->heartbeat = 0;
        }
        flock(backend.lock_fd, LOCK_UN);
        if (failed)
            break;
    }
    /* Stop cannot leave moving targets transmitting at a frozen range. */
    flock(backend.lock_fd, LOCK_EX);
    radar_mute(&device);
    m->mask = 0;
    m->heartbeat = 0;
    unlink("/tmp/radar-motion.ready");
    radar_motion_close(m);
    radar_linux_close(&backend);
    close(singleton);
    return failed;
}
