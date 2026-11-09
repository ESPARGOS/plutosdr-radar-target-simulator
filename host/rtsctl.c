#include "radar_control.h"
#include "radar_linux.h"
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <limits.h>
#include <string.h>

static void print_status(radar_device *device) {
    radar_scene scene;
    radar_get_scene(device, &scene);
    uint32_t version = device->io->read_register(device->context, RADAR_REG_VERSION);
    bool busy = device->io->read_register(device->context, RADAR_REG_STATUS) & 1;
    bool clipped = device->io->read_register(device->context, RADAR_REG_CLIPPED) != 0;
    printf("{\"signature\":\"RTS1\",\"version\":%u,\"sample_rate_hz\":%lu,"
           "\"max_delay_samples\":%u,\"busy\":%s,\"clipped\":%s,\"mask\":%u,\"targets\":[",
           version, radar_sample_rate(device), radar_max_delay(device), busy ? "true" : "false",
           clipped ? "true" : "false", scene.mask);
    for (unsigned i = 0; i < RADAR_TARGETS; ++i) {
        radar_target *target = &scene.targets[i];
        printf(
            "%s{\"delay_samples\":%u,\"phase_increment\":%d,\"gain_q15\":%u,\"fraction_q16\":%u}",
            i ? "," : "", target->delay, (int32_t)target->phase, target->gain, target->fraction);
    }
    puts("]}");
}

int main(int argc, char **argv) {
    unsigned bandwidth = 0;
    bool set_bandwidth = argc == 3 && !strcmp(argv[1], "bandwidth");
    if (set_bandwidth) {
        char *end;
        errno = 0;
        unsigned long value = strtoul(argv[2], &end, 10);
        if (errno || !*argv[2] || *end || value > UINT_MAX || value < 200000) {
            fputs("Invalid bandwidth in Hz\n", stderr);
            return 2;
        }
        bandwidth = (unsigned)value;
    } else if (argc != 2 ||
               (strcmp(argv[1], "status") && strcmp(argv[1], "apply") && strcmp(argv[1], "mute"))) {
        fputs("usage: rtsctl status|apply|mute|bandwidth HZ\n", stderr);
        return 2;
    }
    radar_scene scene;
    if (!strcmp(argv[1], "apply")) {
        char input[1025];
        size_t size = fread(input, 1, sizeof(input) - 1, stdin);
        input[size] = 0;
        if (ferror(stdin) || !feof(stdin) || memchr(input, 0, size) ||
            radar_parse_scene(input, &scene)) {
            fputs("Invalid scene: expected a mask and four target rows\n", stderr);
            return 2;
        }
    }
    radar_device device;
    radar_linux backend;
    if (radar_linux_open(&device, &backend)) {
        fprintf(stderr, "%s\n", device.error);
        return 1;
    }
    int result = 0;
    if (set_bandwidth)
        result = radar_set_bandwidth(&device, bandwidth);
    else if (!strcmp(argv[1], "apply")) {
        result = radar_apply(&device, &scene);
    } else if (!strcmp(argv[1], "mute"))
        result = radar_mute(&device);
    if (!result)
        result = radar_snapshot(&device);
    if (result)
        fprintf(stderr, "%s\n", device.error);
    else
        print_status(&device);
    radar_linux_close(&backend);
    return result ? 1 : 0;
}
