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

static int invalid(radar_device *device, const char *message) {
    device->error = message;
    return RADAR_INVALID;
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
    bool fractional = !strncmp(text, "fractional\n", 11);
    if (fractional)
        text += 11;
    unsigned stride = fractional ? 4 : 3;
    uint32_t words[1 + RADAR_TARGETS * 4];
    for (unsigned i = 0; i < 1 + RADAR_TARGETS * stride; ++i) {
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
        radar_target target = {words[1 + stride * i], words[2 + stride * i], words[3 + stride * i],
                               fractional ? words[4 + stride * i] : 0};
        if (target.delay > RADAR_MAX_DELAY || target.gain > RADAR_MAX_GAIN ||
            target.phase == 0x80000000u || target.fraction > 65535)
            return -1;
        scene->targets[i] = target;
    }
    return 0;
}

bool radar_fpga_motion(radar_device *device) {
    uint32_t version = device->io->read_register(device->context, RADAR_REG_VERSION);
    return version >= 0x00020000 && version <= 0x00020003;
}
unsigned radar_max_delay(radar_device *device) {
    return device->io->read_register(device->context, RADAR_REG_MAX_DELAY);
}
int radar_snapshot(radar_device *device) {
    if (radar_wait_idle(device))
        return -1;
    if (!radar_fpga_motion(device))
        return 0;
    device->io->write_register(device->context, RADAR_REG_COMMIT, 4);
    return radar_wait_idle(device);
}
int radar_apply_motion(radar_device *device, const radar_scene *scene, unsigned moving,
                       unsigned position_edits, unsigned velocity_edits, unsigned upper) {
    bool hardware_motion = radar_fpga_motion(device);
    unsigned maximum = radar_max_delay(device);
    if (scene->mask >= (1u << RADAR_TARGETS) || moving > 15 || position_edits > 15 ||
        velocity_edits > 15 || upper < 1 || upper > maximum)
        return invalid(device, "Invalid target or movement settings");
    if (moving && !hardware_motion)
        return invalid(device, "FPGA motion unavailable");
    double carrier = 1;
    unsigned long rate = 0;
    if (moving) {
        rate = radar_sample_rate(device);
        if (!rate || radar_read_number(device, "out_altvoltage0_RX_LO_frequency", &carrier) ||
            carrier <= 0)
            return fail(device, "Motion clock or carrier unavailable");
    }
    int64_t steps[RADAR_TARGETS] = {0};
    for (unsigned i = 0; i < RADAR_TARGETS; ++i) {
        const radar_target *target = &scene->targets[i];
        if (target->delay > maximum || (target->delay == maximum && target->fraction) ||
            target->gain > RADAR_MAX_GAIN || target->phase == 0x80000000u ||
            target->fraction > 65535 || (!hardware_motion && target->fraction))
            return invalid(device, "Target value out of range");
        if (moving & (1u << i)) {
            double step = -(int32_t)target->phase * (double)rate / 4294967296.0 / carrier;
            if (fabs(step) >= .5)
                return invalid(device, "Movement exceeds half a delay sample per input sample");
            steps[i] = llround(step * 281474976710656.0);
        }
    }
    if (radar_wait_idle(device))
        return -1;
    for (unsigned i = 0; i < RADAR_TARGETS; ++i) {
        unsigned base = RADAR_REG_TARGET_BASE + 4 * i;
        device->io->write_register(device->context, base, scene->targets[i].delay);
        device->io->write_register(device->context, base + 1, scene->targets[i].phase);
        device->io->write_register(device->context, base + 2, scene->targets[i].gain);
        if (hardware_motion) {
            device->io->write_register(device->context, base + 3, scene->targets[i].fraction);
            uint64_t step = (uint64_t)steps[i];
            device->io->write_register(device->context, RADAR_REG_STEP_BASE + 2 * i,
                                       (uint32_t)step);
            device->io->write_register(device->context, RADAR_REG_STEP_BASE + 2 * i + 1,
                                       (uint32_t)(step >> 32) & 65535);
        }
    }
    if (hardware_motion) {
        device->io->write_register(device->context, RADAR_REG_MOTION,
                                   moving | position_edits << 4 | velocity_edits << 8);
        device->io->write_register(device->context, RADAR_REG_UPPER, upper);
    }
    device->io->write_register(device->context, RADAR_REG_ENABLE, scene->mask);
    return radar_commit(device);
}
int radar_apply(radar_device *device, const radar_scene *scene) {
    return radar_apply_motion(device, scene, 0, 15, 15, radar_max_delay(device));
}

int radar_mute(radar_device *device) {
    /* Muting needs only the FPGA. A broken IIO attribute must not block it. */
    if (radar_wait_idle(device))
        return -1;
    if (radar_fpga_motion(device)) {
        /* Muting pauses the live trajectory. Reusing the preceding edit masks
           would reload the position from the last manual scene update. */
        unsigned moving = device->io->read_register(device->context, RADAR_REG_MOTION) & 15;
        device->io->write_register(device->context, RADAR_REG_MOTION, moving);
    }
    device->io->write_register(device->context, RADAR_REG_ENABLE, 0);
    return radar_commit(device);
}

void radar_get_scene(radar_device *device, radar_scene *scene) {
    scene->mask = device->io->read_register(device->context, RADAR_REG_ENABLE);
    for (unsigned i = 0; i < RADAR_TARGETS; ++i) {
        unsigned base =
            (radar_fpga_motion(device) ? RADAR_REG_SNAPSHOT : RADAR_REG_TARGET_BASE) + 4 * i;
        scene->targets[i] = (radar_target){
            device->io->read_register(device->context, base),
            device->io->read_register(device->context, base + 1),
            device->io->read_register(device->context, base + 2),
            radar_fpga_motion(device) ? device->io->read_register(device->context, base + 3) : 0};
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

static int write_integer(radar_device *device, const char *attribute, double value) {
    char text[48];
    snprintf(text, sizeof(text), "%.0f", value);
    return device->io->write_attribute(device->context, attribute, text);
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

static bool integer_range(radar_device *device, const char *attribute, uint64_t *minimum,
                          uint64_t *maximum) {
    char text[128];
    unsigned long long first, step, last;
    int consumed = 0;
    if (device->io->read_attribute(device->context, attribute, text, sizeof(text)) ||
        sscanf(text, "[%llu %llu %llu] %n", &first, &step, &last, &consumed) != 3 || !consumed ||
        text[consumed] || first > last || step != 1)
        return false;
    *minimum = first;
    *maximum = last;
    return true;
}

void radar_carrier_limits(radar_device *device, uint64_t *minimum, uint64_t *maximum) {
    /* Older drivers may omit available ranges. Use the specified AD9363 band
       in that case, and expose the extended band only when both LOs report it. */
    *minimum = 325000000ULL;
    *maximum = 3800000000ULL;
    uint64_t low = 70000000ULL, high = 6000000000ULL;
    const char *attributes[] = {"out_altvoltage0_RX_LO_frequency_available",
                                "out_altvoltage1_TX_LO_frequency_available"};
    for (unsigned i = 0; i < 2; ++i) {
        uint64_t first, last;
        if (!integer_range(device, attributes[i], &first, &last))
            return;
        if (first > low)
            low = first;
        if (last < high)
            high = last;
    }
    if (low <= high) {
        *minimum = low;
        *maximum = high;
    }
}

bool radar_wide_bandwidth_available(radar_device *device) {
    unsigned version = device->io->read_register(device->context, RADAR_REG_VERSION);
    unsigned rate = radar_sample_rate(device);
    if (!((version == 0x00020001 && rate == 160000000) ||
          (version == 0x00020002 && (rate == 160000000 || rate == 61440000)) ||
          (version == 0x00020003 && rate == 61440000)))
        return false;
    uint64_t carrier_low, carrier_high;
    radar_carrier_limits(device, &carrier_low, &carrier_high);
    if (carrier_low > 70000000ULL || carrier_high < 6000000000ULL)
        return false;
    const char *attributes[] = {"in_voltage_rf_bandwidth_available",
                                "out_voltage_rf_bandwidth_available"};
    for (unsigned i = 0; i < 2; ++i) {
        uint64_t low, high;
        if (!integer_range(device, attributes[i], &low, &high) || low > 20000000 ||
            high < (i == 0 ? 56000000 : 40000000))
            return false;
    }
    return true;
}

unsigned radar_max_bandwidth(radar_device *device) {
    if (!radar_wide_bandwidth_available(device))
        return 20000000;
    unsigned version = device->io->read_register(device->context, RADAR_REG_VERSION);
    return radar_sample_rate(device) == 61440000 && version != 0x00020003
               ? 30720000 : 56000000;
}

int radar_set_bandwidth(radar_device *device, unsigned hz) {
    unsigned maximum = radar_max_bandwidth(device);
    if (hz < 200000 || hz > maximum) {
        fail(device, "Bandwidth is unavailable with the current radio and FPGA profile");
        return RADAR_INVALID;
    }
    if (radar_mute(device))
        return -1;
    const char *rx = "in_voltage_rf_bandwidth", *tx = "out_voltage_rf_bandwidth";
    double old_rx, old_tx;
    if (radar_read_number(device, rx, &old_rx) || radar_read_number(device, tx, &old_tx))
        return fail(device, "Cannot read bandwidth; targets muted");
    /* Extended ADI configurations accept 56 MHz TX even when the available
       attribute lists 40 MHz. The analog calibration saturates, not the API. */
    if (write_integer(device, rx, hz) || write_integer(device, tx, hz) ||
        !number_matches(device, rx, hz, 1) || !number_matches(device, tx, hz, 1)) {
        bool restored = !write_integer(device, rx, old_rx);
        if (write_integer(device, tx, old_tx) || !number_matches(device, rx, old_rx, 1) ||
            !number_matches(device, tx, old_tx, 1))
            restored = false;
        return fail(device,
                    restored ? "Bandwidth update failed; previous setting restored; targets muted"
                             : "Bandwidth update failed; targets muted; check radio settings");
    }
    return 0;
}

int radar_set_carrier(radar_device *device, uint64_t hz) {
    uint64_t minimum, maximum;
    radar_carrier_limits(device, &minimum, &maximum);
    if (hz < minimum || hz > maximum) {
        fail(device, "Carrier is outside the radio's tuning range");
        return RADAR_INVALID;
    }
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
    if (radar_fpga_motion(device)) {
        unsigned moving = device->io->read_register(device->context, RADAR_REG_MOTION) & 15;
        if (moving) {
            /* Doppler is unchanged by a carrier edit, but its corresponding
               radial speed changes. Recompute the delay slope before unmute. */
            if (radar_snapshot(device))
                return -1;
            radar_scene scene;
            radar_get_scene(device, &scene);
            unsigned upper = device->io->read_register(device->context, RADAR_REG_UPPER);
            return radar_apply_motion(device, &scene, moving, 0, 15, upper);
        }
    }
    return 0;
}
