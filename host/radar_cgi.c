/* HTTP controls for the Pluto web UI. */
#include "radar_control.h"
#include "radar_linux.h"
#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

typedef enum { STATE, APPLY, MUTE, CARRIER, GAIN } operation;
typedef struct {
    operation operation;
    radar_scene scene;
    uint64_t carrier;
    bool tx;
    double gain;
} request;

static void error_response(int code, const char *message) {
    /* All messages are fixed strings from the control layer, never user input. */
    printf("Status: %d\r\nContent-Type: application/json\r\nCache-Control: no-store\r\n\r\n"
           "{\"error\":\"%s\"}\n",
           code, message);
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
        if (radar_parse_scene(body, &result->scene)) {
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
        if (errno || result->carrier < 325000000ULL || result->carrier > 3800000000ULL) {
            error_response(400, "Carrier must be between 325 and 3800 MHz");
            return -1;
        }
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

static void state_response(radar_device *device, bool muted) {
    radar_scene scene;
    radar_get_scene(device, &scene);
    unsigned long rate = radar_sample_rate(device);
    double fs = rate ? (double)rate : NAN;
    double frequency = read_number(device, "out_altvoltage0_RX_LO_frequency");
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
    bool clipped = device->io->read_register(device->context, RADAR_REG_CLIPPED) != 0;
    double latency = version == 0x00010010 && rate == 160000000 && rx_bandwidth == 20000000 &&
                             tx_bandwidth == 20000000
                         ? .325
                         : NAN;
    printf("Content-Type: application/json\r\nCache-Control: no-store\r\n\r\n"
           "{\"mode\":\"hardware\",\"connected\":true,\"error\":null,\"pluto\":\"on-device\","
           "\"max_targets\":%d,\"latency_calibrated\":false,\"muted\":%s,\"clipped\":%s,"
           "\"radio_available\":%s,\"warning\":%s",
           RADAR_TARGETS, muted ? "true" : "false", clipped ? "true" : "false",
           radio_available ? "true" : "false",
           radio_available ? "null" : "\"Some radio settings could not be read\"");
    json_number("sample_rate_hz", fs);
    json_number("frequency_hz", frequency);
    json_number("max_delay_us", RADAR_MAX_DELAY * 1e6 / fs);
    json_number("delay_step_us", 1e6 / fs);
    json_number("doppler_step_hz", fs / 4294967296.0);
    json_number("rx_bandwidth_hz", rx_bandwidth);
    json_number("tx_bandwidth_hz", tx_bandwidth);
    json_number("rx_gain_db", rx_gain);
    json_number("tx_gain_db", tx_gain);
    json_number("rx_gain_min_db", rx_limits_ok ? rx_limits.minimum : NAN);
    json_number("rx_gain_step_db", rx_limits_ok ? rx_limits.step : NAN);
    json_number("rx_gain_max_db", rx_limits_ok ? rx_limits.maximum : NAN);
    json_number("tx_gain_min_db", tx_limits_ok ? tx_limits.minimum : NAN);
    json_number("tx_gain_step_db", tx_limits_ok ? tx_limits.step : NAN);
    json_number("tx_gain_max_db", tx_limits_ok ? tx_limits.maximum : NAN);
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
        json_number("delay_us", target->delay * 1e6 / fs);
        json_number("doppler_hz", (int32_t)target->phase * fs / 4294967296.0);
        json_number("gain_db", target->gain ? fmax(-90, 20 * log10(target->gain / 32768.0)) : -90);
        fputc('}', stdout);
    }
    puts("]}");
}

int main(void) {
    request input = {0};
    if (parse_request(&input))
        return 0;
#ifndef RADAR_TEST
    if (access("/tmp/radar-loaded", F_OK)) {
        error_response(503, "Radar FPGA is not ready");
        return 0;
    }
#endif
    radar_device device;
    radar_linux backend;
    if (radar_linux_open(&device, &backend)) {
        error_response(503, device.error);
        return 0;
    }
    int result;
    switch (input.operation) {
    case APPLY:
        result = radar_apply(&device, &input.scene);
        break;
    case MUTE:
        result = radar_mute(&device);
        break;
    case CARRIER:
        result = radar_set_carrier(&device, input.carrier);
        break;
    case GAIN:
        result = radar_set_gain(&device, input.tx, input.gain);
        break;
    default:
        result = radar_wait_idle(&device);
        break;
    }
    if (result)
        error_response(result == RADAR_INVALID ? 400 : 503, device.error);
    else
        state_response(&device, input.operation == MUTE);
    radar_linux_close(&backend);
    return 0;
}
