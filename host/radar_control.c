#include "radar_control.h"
#include <ctype.h>
#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int fail(radar_device *device, const char *message) {
    device->error = message;
    return -1;
}

int radar_check(radar_device *device) {
    if (device->io->read_register(device->context, RADAR_REG_SIGNATURE) != RADAR_SIGNATURE)
        return fail(device, "Radar FPGA signature missing");
    return 0;
}

int radar_wait_idle(radar_device *device) {
    for (unsigned i = 0; i < 1000; ++i) {
        if (!(device->io->read_register(device->context, RADAR_REG_STATUS) & 1))
            return 0;
        device->io->sleep_ms(device->context, 1);
    }
    return fail(device, "FPGA configuration timed out");
}

int radar_commit(radar_device *device) {
    device->io->write_register(device->context, RADAR_REG_COMMIT, 1);
    return radar_wait_idle(device);
}

int radar_parse_scene(const char *text, radar_scene *scene) {
    uint32_t words[1 + RADAR_TARGETS * 3];
    for (unsigned i = 0; i < sizeof(words) / sizeof(words[0]); ++i) {
        while (isspace((unsigned char)*text))
            ++text;
        if (*text < '0' || *text > '9')
            return -1;
        char *end;
        errno = 0;
        unsigned long long value = strtoull(text, &end, 10);
        if (errno || value > UINT32_MAX)
            return -1;
        if (*end && !isspace((unsigned char)*end))
            return -1;
        words[i] = (uint32_t)value;
        text = end;
    }
    while (isspace((unsigned char)*text))
        ++text;
    if (*text || words[0] >= (1u << RADAR_TARGETS))
        return -1;
    scene->mask = words[0];
    for (unsigned i = 0; i < RADAR_TARGETS; ++i) {
        radar_target target = {words[1 + 3 * i], words[2 + 3 * i], words[3 + 3 * i]};
        if (target.delay > RADAR_MAX_DELAY || target.gain > RADAR_MAX_GAIN ||
            target.phase == 0x80000000u)
            return -1;
        scene->targets[i] = target;
    }
    return 0;
}

int radar_apply(radar_device *device, const radar_scene *scene) {
    if (scene->mask >= (1u << RADAR_TARGETS))
        return fail(device, "Invalid target mask");
    for (unsigned i = 0; i < RADAR_TARGETS; ++i) {
        const radar_target *target = &scene->targets[i];
        if (target->delay > RADAR_MAX_DELAY || target->gain > RADAR_MAX_GAIN ||
            target->phase == 0x80000000u)
            return fail(device, "Target value out of range");
    }
    if (radar_wait_idle(device))
        return -1;
    for (unsigned i = 0; i < RADAR_TARGETS; ++i) {
        unsigned base = RADAR_REG_TARGET_BASE + 4 * i;
        device->io->write_register(device->context, base, scene->targets[i].delay);
        device->io->write_register(device->context, base + 1, scene->targets[i].phase);
        device->io->write_register(device->context, base + 2, scene->targets[i].gain);
    }
    device->io->write_register(device->context, RADAR_REG_ENABLE, scene->mask);
    return radar_commit(device);
}

int radar_mute(radar_device *device) {
    /* Muting needs only the FPGA. A broken IIO attribute must not block it. */
    if (radar_wait_idle(device))
        return -1;
    device->io->write_register(device->context, RADAR_REG_ENABLE, 0);
    return radar_commit(device);
}

void radar_get_scene(radar_device *device, radar_scene *scene) {
    scene->mask = device->io->read_register(device->context, RADAR_REG_ENABLE);
    for (unsigned i = 0; i < RADAR_TARGETS; ++i) {
        unsigned base = RADAR_REG_TARGET_BASE + 4 * i;
        scene->targets[i] = (radar_target){device->io->read_register(device->context, base),
                                           device->io->read_register(device->context, base + 1),
                                           device->io->read_register(device->context, base + 2)};
    }
}

int radar_read_number(radar_device *device, const char *attribute, double *value) {
    char text[128], *end;
    if (device->io->read_attribute(device->context, attribute, text, sizeof(text)))
        return -1;
    errno = 0;
    double number = strtod(text, &end);
    if (errno || end == text || !isfinite(number))
        return -1;
    while (isspace((unsigned char)*end))
        ++end;
    /* IIO hardwaregain values can include a unit suffix. */
    if (*end && strcmp(end, "dB"))
        return -1;
    *value = number;
    return 0;
}

unsigned long radar_sample_rate(radar_device *device) {
    double rate;
    if (radar_read_number(device, "in_voltage_sampling_frequency", &rate) || rate <= 0 ||
        rate > 1e9)
        return 0;
    return (unsigned long)(floor(rate / 1000 + .5) * 1000);
}

static const char *gain_attribute(bool tx) {
    return tx ? "out_voltage0_hardwaregain" : "in_voltage0_hardwaregain";
}

int radar_get_gain_limits(radar_device *device, bool tx, radar_gain_limits *limits) {
    char text[128];
    const char *attribute =
        tx ? "out_voltage0_hardwaregain_available" : "in_voltage0_hardwaregain_available";
    if (device->io->read_attribute(device->context, attribute, text, sizeof(text)))
        return fail(device, "Cannot read gain limits");
    /* Some older Pluto drivers expose only this first TX attenuation value.
       UG-570 specifies the fixed TX range: -89.75 to 0 dB in 0.25 dB steps. */
    if (tx && !strcmp(text, "[-89.750000]")) {
        *limits = (radar_gain_limits){.minimum = -89.75, .step = .25, .maximum = 0};
        return 0;
    }
    int consumed = 0;
    if (sscanf(text, "[%lf %lf %lf] %n", &limits->minimum, &limits->step, &limits->maximum,
               &consumed) != 3 ||
        !consumed || text[consumed] || !isfinite(limits->minimum) || !isfinite(limits->maximum) ||
        !isfinite(limits->step) || limits->step <= 0 || limits->minimum > limits->maximum)
        return fail(device, "Cannot read gain limits");
    return 0;
}

static int write_number(radar_device *device, const char *attribute, double value) {
    char text[48];
    snprintf(text, sizeof(text), "%.6f", value);
    return device->io->write_attribute(device->context, attribute, text);
}

static int number_matches(radar_device *device, const char *attribute, double expected,
                          double tolerance) {
    double actual;
    return !radar_read_number(device, attribute, &actual) && fabs(actual - expected) <= tolerance;
}

int radar_set_gain(radar_device *device, bool tx, double gain) {
    radar_gain_limits limits;
    if (radar_get_gain_limits(device, tx, &limits))
        return -1;
    if (!isfinite(gain) || gain < limits.minimum || gain > limits.maximum ||
        fabs((gain - limits.minimum) / limits.step - round((gain - limits.minimum) / limits.step)) >
            1e-5) {
        fail(device, "Gain is outside the supported range or step");
        return RADAR_INVALID;
    }
    const char *attribute = gain_attribute(tx);
    const char *mode_attribute = "in_voltage0_gain_control_mode";
    char old_mode[40];
    double old_gain;
    if (radar_read_number(device, attribute, &old_gain) ||
        (!tx &&
         device->io->read_attribute(device->context, mode_attribute, old_mode, sizeof(old_mode))))
        return fail(device, "Cannot read current gain");
    if ((!tx && device->io->write_attribute(device->context, mode_attribute, "manual")) ||
        write_number(device, attribute, gain) || !number_matches(device, attribute, gain, .001)) {
        bool restored = !write_number(device, attribute, old_gain);
        if (!tx) {
            if (device->io->write_attribute(device->context, mode_attribute, old_mode))
                restored = false;
            char actual_mode[40];
            if (device->io->read_attribute(device->context, mode_attribute, actual_mode,
                                           sizeof(actual_mode)) ||
                strcmp(actual_mode, old_mode))
                restored = false;
        }
        if (!number_matches(device, attribute, old_gain, .001))
            restored = false;
        return fail(device, restored ? "Gain update failed; previous setting restored"
                                     : "Gain update failed; check radio settings");
    }
    return 0;
}

int radar_set_carrier(radar_device *device, uint64_t hz) {
    if (hz < 325000000ULL || hz > 3800000000ULL)
        return fail(device, "Carrier must be between 325 and 3800 MHz");
    if (radar_mute(device))
        return -1;
    const char *rx = "out_altvoltage0_RX_LO_frequency", *tx = "out_altvoltage1_TX_LO_frequency";
    double old_rx, old_tx;
    if (radar_read_number(device, rx, &old_rx) || radar_read_number(device, tx, &old_tx))
        return fail(device, "Cannot read carrier frequency; targets muted");
    char value[32];
    snprintf(value, sizeof(value), "%llu", (unsigned long long)hz);
    if (device->io->write_attribute(device->context, rx, value) ||
        device->io->write_attribute(device->context, tx, value) ||
        !number_matches(device, rx, (double)hz, 10) ||
        !number_matches(device, tx, (double)hz, 10)) {
        char previous[32];
        snprintf(previous, sizeof(previous), "%.0f", old_rx);
        bool restored = !device->io->write_attribute(device->context, rx, previous);
        snprintf(previous, sizeof(previous), "%.0f", old_tx);
        if (device->io->write_attribute(device->context, tx, previous))
            restored = false;
        if (!number_matches(device, rx, old_rx, 10) || !number_matches(device, tx, old_tx, 10))
            restored = false;
        return fail(device, restored
                                ? "Tuning failed; previous frequency restored; targets muted"
                                : "Tuning failed; targets muted; radio requires reconfiguration");
    }
    return 0;
}
