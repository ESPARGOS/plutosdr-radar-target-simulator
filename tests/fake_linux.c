/* Linked only into test binaries. Production binaries use radar_linux.c. */
#include "fake_device.h"
#include "radar_linux.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static fake_device fake;
int radar_linux_open(radar_device *device, radar_linux *backend) {
    (void)backend;
    fake_init(&fake, device);
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
