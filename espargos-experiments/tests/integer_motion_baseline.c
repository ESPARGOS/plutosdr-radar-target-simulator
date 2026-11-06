/* Measurement baseline: whole-sample delay updates at 100 Hz on the ARM.
 * Uses the current FPGA and preserves the carrier phase across delay edits.
 * Run only with a single enabled target, initially at an integer delay.
 */
#define _DEFAULT_SOURCE
#include "radar_linux.h"
#include <math.h>
#include <signal.h>
#include <stdio.h>
#include <sys/file.h>
#include <time.h>
#include <unistd.h>
static volatile sig_atomic_t stopped;
static void stop(int sig) {
    (void)sig;
    stopped = 1;
}
static double now(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec * 1e-9;
}
int main(void) {
    signal(SIGTERM, stop);
    signal(SIGINT, stop);
    radar_device d;
    radar_linux b;
    radar_scene scene;
    if (radar_linux_open(&d, &b))
        return 1;
    if (radar_snapshot(&d))
        return 1;
    radar_get_scene(&d, &scene);
    double carrier;
    unsigned rate = radar_sample_rate(&d);
    if (scene.mask != 1 || scene.targets[0].fraction || !rate ||
        radar_read_number(&d, "out_altvoltage0_RX_LO_frequency", &carrier))
        return 2;
    double fd = (int32_t)scene.targets[0].phase * (double)rate / 4294967296.0;
    double start = now(), origin = scene.targets[0].delay;
    flock(b.lock_fd, LOCK_UN);
    int failed = 0;
    unsigned changes = 0;
    while (!stopped && now() - start < 120) {
        usleep(10000);
        flock(b.lock_fd, LOCK_EX);
        if (!(d.io->read_register(d.context, RADAR_REG_ENABLE) & 1)) {
            flock(b.lock_fd, LOCK_UN);
            break;
        }
        double position = origin - fd * rate / carrier * (now() - start);
        if (position < 0 || position > radar_max_delay(&d)) {
            failed = 1;
            break;
        }
        unsigned delay = (unsigned)floor(position + .5);
        if (delay != scene.targets[0].delay) {
            scene.targets[0].delay = delay;
            if (radar_apply(&d, &scene)) {
                failed = 1;
                break;
            }
            ++changes;
        }
        flock(b.lock_fd, LOCK_UN);
    }
    flock(b.lock_fd, LOCK_EX);
    radar_mute(&d);
    radar_linux_close(&b);
    printf("integer motion: %u whole-sample changes, %.6f s, %.9f Hz carrier Doppler\n", changes,
           now() - start, fd);
    return failed;
}
