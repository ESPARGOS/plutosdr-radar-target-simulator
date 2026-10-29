#include "radar_motion.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>

int main(void) {
    radar_scene scene = {.mask = 3, .targets = {{10, (uint32_t)-100, 4096}, {20, 100, 4096}}};
    radar_motion m = {0};
    /* Choose rate/carrier so each phase word is one sample/second. */
    const double rate = 65536, carrier = 1;
    radar_motion_configure(&m, &scene, 3, 15, 15, 100, 0);
    radar_motion_advance(&m, &scene, .003, rate, carrier);
    assert(scene.targets[0].delay == 10 && fabs(m.position[0] - 10.3) < 1e-8);
    radar_motion_advance(&m, &scene, .006, rate, carrier);
    assert(scene.targets[0].delay == 11); /* Accumulate below one delay step. */
    radar_motion_advance(&m, &scene, .2, rate, carrier);
    assert(scene.targets[0].delay == 30 && scene.targets[1].delay == 0);
    assert((int32_t)scene.targets[1].phase == -100); /* Lower reflection. */
    radar_motion_advance(&m, &scene, 1, rate, carrier);
    assert(scene.targets[0].delay == 90 && (int32_t)scene.targets[0].phase == 100);
    radar_motion_advance(&m, &scene, 1001, rate, carrier);
    assert(scene.targets[0].delay == 90); /* Many bounces, no iteration/drift. */
    radar_scene stale = scene;
    stale.targets[0].delay = 2;
    stale.targets[0].phase = (uint32_t)-100;
    radar_motion_configure(&m, &stale, 3, 0, 0, 100, 1001);
    assert(stale.targets[0].delay == 90 && (int32_t)stale.targets[0].phase == 100);
    radar_motion_configure(&m, &stale, 3, 0, 0, 50, 1001);
    assert(stale.targets[0].delay == 50 && (int32_t)stale.targets[0].phase == 100);
    stale.mask = 0;
    radar_motion_advance(&m, &stale, 1100, rate, carrier);
    assert(stale.targets[0].delay == 50); /* Off/mute pauses movement. */
    stale.mask = 3;
    radar_motion_advance(&m, &stale, 1100.1, rate, carrier);
    assert(stale.targets[0].delay == 40);
    stale.targets[0].delay = 25; /* External controller edits rebase the motion. */
    radar_motion_advance(&m, &stale, 1100.2, rate, carrier);
    assert(stale.targets[0].delay == 15);
    puts("PASS: fractional motion, velocity sign, reflections, pause, window changes and stale "
         "edits");
}
