#define _POSIX_C_SOURCE 200809L
/* HTTP controls for the Pluto web UI. */
#include "radar_control.h"
#include "radar_linux.h"
#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#ifndef RADAR_READY_FILE
#define RADAR_READY_FILE "/tmp/radar-loaded"
#endif
#ifndef RADAR_FAILED_FILE
#define RADAR_FAILED_FILE "/tmp/radar-failed"
#endif
#ifndef RADAR_FALLBACK_FILE
#define RADAR_FALLBACK_FILE "/tmp/radar-fallback"
#endif
#ifndef RADAR_STARTUP_FILE
#define RADAR_STARTUP_FILE "/tmp/radar-startup-state"
#endif

#ifndef RADAR_MODE_FILE
#define RADAR_MODE_FILE "/mnt/jffs2/radar-mode"
#endif
#ifndef RADAR_SERVICE
#define RADAR_SERVICE "/etc/init.d/S61radar"
#endif

typedef enum { STATE, APPLY, MUTE, CARRIER, GAIN, BANDWIDTH, RADIO_MODE } operation;

static const char *requested_mode(void) {
    char value[32] = "";
    FILE *file = fopen(RADAR_MODE_FILE, "r");
    if (file) {
        if (!fgets(value, sizeof(value), file))
            value[0] = '\0';
        fclose(file);
    }
    return !strcmp(value, "standard\n") ? "standard" : "overclocked";
}
typedef struct {
    operation operation;
    radar_scene scene;
    uint64_t carrier;
    unsigned bandwidth;
    bool standard;
    bool tx;
    double gain;
    bool motion_request;
    unsigned motion_mask, position_edits, phase_edits, upper;
} request;

static void error_response(int code, const char *message) {
    /* All messages are fixed strings from the control layer, never user input. */
    printf("Status: %d\r\nContent-Type: application/json\r\nCache-Control: no-store\r\n\r\n"
           "{\"error\":\"%s\"}\n",
           code, message);
}

static void startup_response(void) {
    bool failed = access(RADAR_FAILED_FILE, F_OK) == 0;
    bool fallback = access(RADAR_FALLBACK_FILE, F_OK) == 0;
    char stage[32] = "", extra;
    double started = 0, changed = 0, now = 0;
    FILE *file = fopen(RADAR_STARTUP_FILE, "r");
    bool valid = false;
    if (file) {
        valid = fscanf(file, "%lf %lf %31s %c", &started, &changed, stage, &extra) == 3;
        fclose(file);
    }
    file = fopen("/proc/uptime", "r");
    if (file) {
        valid = fscanf(file, "%lf", &now) == 1 && valid;
        fclose(file);
    } else
        valid = false;
    valid = valid && isfinite(started) && isfinite(changed) && started >= 0 && changed >= started &&
            now >= changed;
    const char *label = "Waiting for radar startup";
    const struct {
        const char *key, *label;
    } stages[] = {
        {"radio", "Configuring the radio"},
        {"clocks", "Configuring the overclocked interface"},
        {"standard", "Configuring the standard interface"},
        {"reconfigure", "Restarting the radio"},
        {"fallback", "Restoring normal radio clocks and filters"},
        {"rx_timing", "Calibrating RX interface timing"},
        {"tx_timing", "Calibrating TX interface timing"},
        {"joint_timing", "Checking shared RX/TX timing"},
        {"tx_verify", "Checking TX integrity (5-second startup test)"},
        {"rx_verify", "Checking RX integrity (1-second startup test)"},
        {"ready", "Finishing radar startup"},
    };
    bool known = false;
    for (unsigned i = 0; valid && i < sizeof stages / sizeof *stages; ++i) {
        if (!strcmp(stage, stages[i].key)) {
            label = stages[i].label;
            known = true;
            break;
        }
    }
    printf("Status: 503\r\nContent-Type: application/json\r\nCache-Control: no-store\r\n\r\n"
           "{\"error\":\"%s%s\",\"startup\":{\"failed\":%s,\"elapsed_seconds\":",
           failed     ? "Radar startup failed: "
           : fallback ? "61.44 MHz fallback: "
                      : "",
           label, failed ? "true" : "false");
    if (valid && known)
        printf("%.0f", floor(now - started));
    else
        fputs("null", stdout);
    fputs(",\"stage_elapsed_seconds\":", stdout);
    if (valid && known)
        printf("%.0f", floor(now - changed));
    else
        fputs("null", stdout);
    printf(",\"fallback\":%s,\"expected_seconds\":30}}\n", fallback ? "true" : "false");
}

static int read_body(char *buffer, size_t capacity) {
    const char *length = getenv("CONTENT_LENGTH");
    char *end;
    errno = 0;
    unsigned long count = length ? strtoul(length, &end, 10) : 0;
    if (!length || !*length || *end || errno || !count || count >= capacity)
        return -1;
    if (fread(buffer, 1, count, stdin) != count || memchr(buffer, 0, count))
        return -1;
    buffer[count] = 0;
    return (int)count;
}

static int parse_request(request *result) {
    const char *method = getenv("REQUEST_METHOD"), *path = getenv("PATH_INFO");
    if (!method || !path) {
        error_response(400, "Missing request information");
        return -1;
    }
    if (!strcmp(path, "/state"))
        result->operation = STATE;
    else if (!strcmp(path, "/apply"))
        result->operation = APPLY;
    else if (!strcmp(path, "/mute"))
        result->operation = MUTE;
    else if (!strcmp(path, "/radio"))
        result->operation = CARRIER;
    else if (!strcmp(path, "/gain"))
        result->operation = GAIN;
    else if (!strcmp(path, "/mode"))
        result->operation = RADIO_MODE;
    else if (!strcmp(path, "/bandwidth"))
        result->operation = BANDWIDTH;
    else {
        error_response(404, "Unknown endpoint");
        return -1;
    }
    if (strcmp(method, result->operation == STATE ? "GET" : "POST")) {
        error_response(405, "Invalid method");
        return -1;
    }
    const char *origin = getenv("HTTP_ORIGIN"), *host = getenv("HTTP_HOST");
    if (result->operation != STATE && origin) {
        char expected[300];
        int size = snprintf(expected, sizeof(expected), "http://%s", host ? host : "");
        if (size < 0 || (size_t)size >= sizeof(expected) || strcmp(origin, expected)) {
            error_response(403, "Cross-origin request rejected");
            return -1;
        }
    }
    if (result->operation == STATE || result->operation == MUTE)
        return 0;
    char body[1025];
    int length = read_body(body, sizeof(body));
    if (length < 0) {
        error_response(400, "Invalid or incomplete payload");
        return -1;
    }
    if (result->operation == APPLY) {
        const char *scene = body;
        result->position_edits = result->phase_edits = 15;
        result->upper = RADAR_MAX_DELAY;
        if (!strncmp(body, "motion ", 7)) {
            int consumed = 0;
            const char *newline = strchr(body, '\n');
            if (!newline ||
                sscanf(body, "motion %u %u %u %u%n", &result->motion_mask, &result->position_edits,
                       &result->phase_edits, &result->upper, &consumed) != 4 ||
                body + consumed != newline || result->motion_mask > 15 ||
                result->position_edits > 15 || result->phase_edits > 15 || result->upper < 1 ||
                result->upper > RADAR_MAX_DELAY) {
                error_response(400, "Invalid movement settings");
                return -1;
            }
            result->motion_request = true;
            scene = newline + 1;
        }
        if (radar_parse_scene(scene, &result->scene)) {
            error_response(400, "Invalid target mask or register values");
            return -1;
        }
    } else if (result->operation == CARRIER) {
        if (length > 16 || strspn(body, "0123456789") != (size_t)length) {
            error_response(400, "Frequency must be integer Hz");
            return -1;
        }
        errno = 0;
        result->carrier = strtoull(body, NULL, 10);
        if (errno || result->carrier < 70000000ULL || result->carrier > 6000000000ULL) {
            error_response(400, "Carrier must be between 70 and 6000 MHz");
            return -1;
        }
    } else if (result->operation == RADIO_MODE) {
        if (strcmp(body, "standard") && strcmp(body, "overclocked")) {
            error_response(400, "Mode must be standard or overclocked");
            return -1;
        }
        result->standard = !strcmp(body, "standard");
    } else if (result->operation == BANDWIDTH) {
        if (length > 8 || strspn(body, "0123456789") != (size_t)length) {
            error_response(400, "Bandwidth must be integer Hz");
            return -1;
        }
        unsigned long hz = strtoul(body, NULL, 10);
        if (hz < 200000 || hz > 56000000) {
            error_response(400, "Bandwidth must be from 200000 to 56000000 Hz");
            return -1;
        }
        result->bandwidth = (unsigned)hz;
    } else {
        char channel[3];
        int consumed = 0;
        if (length > 48 || sscanf(body, "%2s %lf %n", channel, &result->gain, &consumed) != 2 ||
            consumed != length || !isfinite(result->gain) ||
            (strcmp(channel, "rx") && strcmp(channel, "tx"))) {
            error_response(400, "Expected rx or tx and a finite gain in dB");
            return -1;
        }
        result->tx = !strcmp(channel, "tx");
    }
    return 0;
}

static double read_number(radar_device *device, const char *name) {
    double value;
    return radar_read_number(device, name, &value) ? NAN : value;
}

static void json_number(const char *name, double value) {
    printf(",\"%s\":", name);
    if (isfinite(value))
        printf("%.12g", value);
    else
        fputs("null", stdout);
}

static void state_response(radar_device *device) {
    radar_scene scene;
    radar_get_scene(device, &scene);
    unsigned long rate = radar_sample_rate(device);
    double fs = rate ? (double)rate : NAN;
    double frequency = read_number(device, "out_altvoltage0_RX_LO_frequency");
    uint64_t carrier_minimum, carrier_maximum;
    radar_carrier_limits(device, &carrier_minimum, &carrier_maximum);
    double rx_bandwidth = read_number(device, "in_voltage_rf_bandwidth");
    double tx_bandwidth = read_number(device, "out_voltage_rf_bandwidth");
    double rx_gain = read_number(device, "in_voltage0_hardwaregain");
    double tx_gain = read_number(device, "out_voltage0_hardwaregain");
    radar_gain_limits rx_limits = {NAN, NAN, NAN}, tx_limits = {NAN, NAN, NAN};
    bool rx_limits_ok = !radar_get_gain_limits(device, false, &rx_limits);
    bool tx_limits_ok = !radar_get_gain_limits(device, true, &tx_limits);
    bool radio_available = rate && isfinite(frequency) && isfinite(rx_bandwidth) &&
                           isfinite(tx_bandwidth) && isfinite(rx_gain) && isfinite(tx_gain) &&
                           rx_limits_ok && tx_limits_ok;
    uint32_t version = device->io->read_register(device->context, RADAR_REG_VERSION);
    bool hardware_motion = radar_fpga_motion(device);
    unsigned motion_mask =
        hardware_motion ? device->io->read_register(device->context, RADAR_REG_MOTION) & 15 : 0;
    bool clipped = device->io->read_register(device->context, RADAR_REG_CLIPPED) != 0;
    bool standard = rate == 61440000 && read_number(device, "in_out_voltage_filter_fir_en") == 0;
    bool fallback = standard && access(RADAR_FALLBACK_FILE, F_OK) == 0;
    double latency = NAN;
    if (rx_bandwidth == 20000000 && tx_bandwidth == 20000000) {
        if (hardware_motion)
            latency = rate == 160000000 ? .44375 : standard ? 1.05625 : NAN;
        else if (version == 0x00010010 || version == 0x00010011)
            latency = rate == 160000000 ? .325 : standard ? .78125 : NAN;
    }
    if (version == 0x00020001 && rate == 160000000 && rx_bandwidth == 56000000 &&
        tx_bandwidth >= 40000000 && tx_bandwidth <= 56000000)
        latency = .4078125;
    if (version == 0x00020002) {
        latency = NAN;
        if (rx_bandwidth == 20000000 && tx_bandwidth == 20000000)
            latency = rate == 160000000 ? .45 : standard ? 1.090625 : NAN;
        else if (rate == 160000000 && rx_bandwidth == 56000000 && tx_bandwidth == 56000000)
            latency = .4140625;
        else if (standard && rx_bandwidth == 30720000 && tx_bandwidth == 30720000)
            latency = 1.0734375;
    }
    printf("Content-Type: application/json\r\nCache-Control: no-store\r\n\r\n"
           "{\"mode\":\"hardware\",\"connected\":true,\"error\":null,\"pluto\":\"on-device\","
           "\"max_targets\":%d,\"latency_calibrated\":false,\"muted\":%s,\"clipped\":%s,"
           "\"radio_available\":%s,\"warning\":%s",
           RADAR_TARGETS, scene.mask == 0 ? "true" : "false", clipped ? "true" : "false",
           radio_available ? "true" : "false",
           radio_available ? "null" : "\"Some radio settings could not be read\"");
    printf(",\"fallback\":%s", fallback ? "true" : "false");
    printf(",\"motion_available\":%s", hardware_motion ? "true" : "false");
    json_number("motion_upper_samples",
                hardware_motion ? device->io->read_register(device->context, RADAR_REG_UPPER)
                                : radar_max_delay(device));
    json_number("fractional_delay_bits", hardware_motion ? 10 : 0);
    printf(",\"fpga_motion\":%s", hardware_motion ? "true" : "false");
    json_number("sample_rate_hz", fs);
    json_number("frequency_hz", frequency);
    json_number("max_delay_us", radar_max_delay(device) * 1e6 / fs);
    json_number("delay_step_us", 1e6 / fs / (hardware_motion ? 1024 : 1));
    json_number("doppler_step_hz", fs / 4294967296.0);
    printf(",\"requested_radio_mode\":\"%s\",\"radio_mode\":\"%s\"", requested_mode(),
           rate > 100000000 ? "overclocked" : "standard");
    json_number("rx_bandwidth_hz", rx_bandwidth);
    printf(",\"wideband_available\":%s", radar_wide_bandwidth_available(device) ? "true" : "false");
    json_number("bandwidth_max_hz", radar_max_bandwidth(device));
    json_number("frequency_min_hz", (double)carrier_minimum);
    json_number("frequency_max_hz", (double)carrier_maximum);
    json_number("tx_bandwidth_hz", tx_bandwidth);
    json_number("rx_gain_db", rx_gain);
    json_number("tx_gain_db", tx_gain);
    json_number("rx_gain_min_db", rx_limits_ok ? rx_limits.minimum : NAN);
    json_number("rx_gain_step_db", rx_limits_ok ? rx_limits.step : NAN);
    json_number("rx_gain_max_db", rx_limits_ok ? rx_limits.maximum : NAN);
    json_number("tx_gain_min_db", tx_limits_ok ? tx_limits.minimum : NAN);
    json_number("tx_gain_step_db", tx_limits_ok ? tx_limits.step : NAN);
    json_number("tx_gain_max_db", tx_limits_ok ? tx_limits.maximum : NAN);
    if (version == 0x00020003 && standard) {
        latency = rx_bandwidth == 20000000 && tx_bandwidth == 20000000 ? 1.35 :
                  rx_bandwidth == 56000000 && tx_bandwidth == 56000000 ? 1.31875 : NAN;
    }
    json_number("hardware_latency_us", latency);
    fputs(",\"targets\":[", stdout);
    unsigned emitted = 0;
    for (unsigned i = 0; i < RADAR_TARGETS; ++i) {
        radar_target *target = &scene.targets[i];
        bool enabled = scene.mask & (1u << i);
        if (!target->gain && !enabled)
            continue;
        printf("%s{\"id\":%u,\"enabled\":%s", emitted++ ? "," : "", i + 1,
               enabled ? "true" : "false");
        printf(",\"realistic_movement\":%s", (motion_mask & (1u << i)) ? "true" : "false");
        json_number("delay_us", (target->delay + target->fraction / 65536.0) * 1e6 / fs);
        json_number("doppler_hz", (int32_t)target->phase * fs / 4294967296.0);
        json_number("gain_db", target->gain ? fmax(-90, 20 * log10(target->gain / 32768.0)) : -90);
        fputc('}', stdout);
    }
    puts("]}");
}

/* The CGI returns immediately; polling reports progress from the init script. */
static void switch_mode(radar_device *device, bool standard) {
    if (access(RADAR_SERVICE, R_OK)) {
        error_response(503, "Radio reconfiguration is unavailable");
        return;
    }
    if (radar_mute(device)) {
        error_response(503, device->error);
        return;
    }
    FILE *file = fopen(RADAR_MODE_FILE ".new", "w");
    if (!file) {
        error_response(503, "Cannot save the radio mode");
        return;
    }
    bool saved = fprintf(file, "%s\n", standard ? "standard" : "overclocked") > 0;
    saved = fflush(file) == 0 && saved;
    saved = fsync(fileno(file)) == 0 && saved;
    saved = fclose(file) == 0 && saved;
    if (!saved || rename(RADAR_MODE_FILE ".new", RADAR_MODE_FILE)) {
        unlink(RADAR_MODE_FILE ".new");
        error_response(503, "Cannot save the radio mode");
        return;
    }
    unlink(RADAR_READY_FILE);
    unlink(RADAR_FAILED_FILE);
    unlink(RADAR_FALLBACK_FILE);
    unlink(RADAR_STARTUP_FILE);
    pid_t child = fork();
    if (child < 0) {
        file = fopen(RADAR_FAILED_FILE, "w");
        if (file) fclose(file);
        error_response(503, "Cannot start radio reconfiguration");
        return;
    }
    if (!child) {
        setsid();
        int null = open("/dev/null", O_RDWR);
        if (null >= 0) {
            dup2(null, STDIN_FILENO);
            dup2(null, STDOUT_FILENO);
            dup2(null, STDERR_FILENO);
            if (null > STDERR_FILENO) close(null);
        }
        execl("/bin/sh", "sh", RADAR_SERVICE, "reconfigure", (char *)NULL);
        file = fopen(RADAR_FAILED_FILE, "w");
        if (file) fclose(file);
        _exit(127);
    }
    printf("Status: 202\r\nContent-Type: application/json\r\nCache-Control: no-store\r\n\r\n"
           "{\"connected\":false,\"muted\":true,\"targets\":[],"
           "\"requested_radio_mode\":\"%s\",\"error\":\"Restarting the radio\"}\n",
           standard ? "standard" : "overclocked");
}

int main(void) {
    request input = {0};
    if (parse_request(&input))
        return 0;
    if (access(RADAR_READY_FILE, F_OK) &&
        !(input.operation == RADIO_MODE && access(RADAR_FAILED_FILE, F_OK) == 0)) {
        startup_response();
        return 0;
    }
    radar_device device;
    radar_linux backend;
    if (radar_linux_open(&device, &backend)) {
        error_response(503, device.error);
        return 0;
    }
    /* A mode change may have begun while this CGI waited for the device lock. */
    if (access(RADAR_READY_FILE, F_OK) &&
        !(input.operation == RADIO_MODE && access(RADAR_FAILED_FILE, F_OK) == 0)) {
        radar_linux_close(&backend);
        startup_response();
        return 0;
    }
    if (input.operation == RADIO_MODE) {
        switch_mode(&device, input.standard);
        radar_linux_close(&backend);
        return 0;
    }
    int result;
    switch (input.operation) {
    case APPLY: {
        unsigned upper = input.motion_request ? input.upper : radar_max_delay(&device);
        result = radar_apply_motion(&device, &input.scene, input.motion_mask, input.position_edits,
                                    input.phase_edits, upper);
        break;
    }
    case MUTE:
        result = radar_mute(&device);
        break;
    case CARRIER:
        result = radar_set_carrier(&device, input.carrier);
        break;
    case GAIN:
        result = radar_set_gain(&device, input.tx, input.gain);
        break;
    case BANDWIDTH:
        result = radar_set_bandwidth(&device, input.bandwidth);
        break;
    default:
        result = radar_wait_idle(&device);
        break;
    }
    if (!result)
        result = radar_snapshot(&device);
    if (result)
        error_response(result == RADAR_INVALID ? 400 : 503, device.error);
    else
        state_response(&device);
    radar_linux_close(&backend);
    return 0;
}
