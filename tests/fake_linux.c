/* Linked only into test binaries. Production binaries use radar_linux.c. */
#define _POSIX_C_SOURCE 200809L
#include "fake_device.h"
#include "radar_linux.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static fake_device fake;

/* Keep startup tests independent of the CI runner's age and scheduling. */
FILE *__real_fopen(const char *path, const char *mode);
FILE *__wrap_fopen(const char *path, const char *mode) {
    char *uptime = getenv("RADAR_TEST_UPTIME");
    if (uptime && !strcmp(path, "/proc/uptime"))
        return fmemopen(uptime, strlen(uptime), "r");
    return __real_fopen(path, mode);
}

int radar_linux_open(radar_device *device, radar_linux *backend) {
    (void)backend;
    fake_init(&fake, device);
    if (getenv("RADAR_TEST_EXTENDED") || getenv("RADAR_TEST_WIDEBAND")) {
        strcpy(fake.values[11], "[70000000 1 6000000000]");
        strcpy(fake.values[12], "[46875001 1 6000000000]");
    }
    if (getenv("RADAR_TEST_FRACTIONAL")) {
        fake.registers[RADAR_REG_VERSION] = 0x20000;
        fake.registers[RADAR_REG_MAX_DELAY] = 12276;
        fake.registers[RADAR_REG_FRACTION_BITS] = 10;
        fake.registers[RADAR_REG_UPPER] = 12276;
    }
    if (getenv("RADAR_TEST_WIDEBAND")) {
        fake.registers[RADAR_REG_VERSION] = 0x20001;
        fake.registers[RADAR_REG_MAX_DELAY] = 12276;
        fake.registers[RADAR_REG_FRACTION_BITS] = 10;
        strcpy(fake.values[13], "[200000 1 56000000]");
        strcpy(fake.values[14], "[200000 1 40000000]");
    }
    if (getenv("RADAR_TEST_EIGHT_TAPS"))
        fake.registers[RADAR_REG_VERSION] = 0x20002;
    const char *mask = getenv("RADAR_TEST_MASK");
    if (mask)
        fake.registers[RADAR_REG_ENABLE] = (unsigned)strtoul(mask, NULL, 10);
    const char *rate = getenv("RADAR_TEST_RATE");
    if (rate)
        snprintf(fake.values[0], sizeof(fake.values[0]), "%s", rate);
    fake.missing_radio = getenv("RADAR_TEST_NO_RADIO") != NULL;
    fake.stuck = getenv("RADAR_TEST_BUSY") != NULL;
    fake.fail_read = getenv("RADAR_TEST_FAIL_READ");
    const char *fail_write = getenv("RADAR_TEST_FAIL_WRITE");
    fake.fail_write_at = fail_write ? (unsigned)strtoul(fail_write, NULL, 10) : 0;
    fake.fail_rollback = getenv("RADAR_TEST_FAIL_ROLLBACK") != NULL;
    return 0;
}
void radar_linux_close(radar_linux *backend) {
    (void)backend;
    fprintf(stderr, "TEST_STATE={\"mask\":%u,\"writes\":%u,\"rx_gain\":\"%s\",\"mode\":\"%s\"}\n",
            fake.registers[RADAR_REG_ENABLE], fake.register_writes,
            fake_value(&fake, "in_voltage0_hardwaregain"),
            fake_value(&fake, "in_voltage0_gain_control_mode"));
}
