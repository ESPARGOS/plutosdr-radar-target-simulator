#include "fake_device.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    fake_device fake;
    radar_device device;
    fake_init(&fake, &device);
    fake.missing_radio = true;
    assert(!radar_mute(&device));
    assert(fake.registers[RADAR_REG_ENABLE] == 0);
    assert(fake.attribute_reads == 0 && fake.attribute_writes == 0);

    fake_init(&fake, &device);
    fake.stuck = true;
    assert(radar_mute(&device) < 0);
    assert(fake.sleeps == 1000 && fake.register_writes == 0);

    radar_scene scene;
    assert(!radar_parse_scene("15\n0 4294967295 32767\n1 0 1\n2047 1 0\n4 20 8192\n", &scene));
    fake_init(&fake, &device);
    assert(!radar_apply(&device, &scene));
    assert(fake.registers[RADAR_REG_TARGET_BASE + 1] == UINT32_MAX);
    assert(fake.attribute_reads == 0);
    scene.targets[2].delay = 2048;
    unsigned writes = fake.register_writes;
    assert(radar_apply(&device, &scene) < 0 && fake.register_writes == writes);
    const char *invalid[] = {"0 -1 0 1 0 0 0 0 0 0 0 0 0",    "0 0 2147483648 1 0 0 0 0 0 0 0 0 0",
                             "16 0 0 0 0 0 0 0 0 0 0 0 0",    "0 0 4294967296 0 0 0 0 0 0 0 0 0 0",
                             "0 0 0 32768 0 0 0 0 0 0 0 0 0", "0 0 0 0 0 0 0 0 0 0 0 0 0 trailing"};
    for (unsigned i = 0; i < sizeof(invalid) / sizeof(invalid[0]); ++i)
        assert(radar_parse_scene(invalid[i], &scene) < 0);

    fake_init(&fake, &device);
    assert(radar_sample_rate(&device) == 160000000);
    assert(radar_set_gain(&device, false, 30.5) == RADAR_INVALID);
    assert(fake.attribute_writes == 0);
    assert(!radar_set_gain(&device, false, 30));
    assert(!strcmp(fake_value(&fake, "in_voltage0_gain_control_mode"), "manual"));
    assert(!strcmp(fake_value(&fake, "in_voltage0_hardwaregain"), "30.000000"));
    assert(fake.register_writes == 0);

    fake_init(&fake, &device);
    fake.fail_write_at = 2; /* Mode changes, but writing gain fails. */
    assert(radar_set_gain(&device, false, 30) < 0);
    assert(strstr(device.error, "previous setting restored"));
    assert(!strcmp(fake_value(&fake, "in_voltage0_gain_control_mode"), "slow_attack"));
    assert(!strcmp(fake_value(&fake, "in_voltage0_hardwaregain"), "35.000000"));

    fake_init(&fake, &device);
    fake.fail_write_at = 2;
    fake.fail_rollback = true;
    assert(radar_set_gain(&device, false, 30) < 0);
    assert(strstr(device.error, "check radio settings"));

    fake_init(&fake, &device);
    fake.fail_write_at = 2; /* RX retunes, TX fails; restore both. */
    assert(radar_set_carrier(&device, 2400000000ULL) < 0);
    assert(fake.registers[RADAR_REG_ENABLE] == 0);
    assert(strstr(device.error, "previous frequency restored"));
    assert(!strcmp(fake_value(&fake, "out_altvoltage0_RX_LO_frequency"), "2380000000"));
    assert(!strcmp(fake_value(&fake, "out_altvoltage1_TX_LO_frequency"), "2380000000"));

    fake_init(&fake, &device);
    fake.fail_write_at = 2;
    fake.fail_rollback = true;
    assert(radar_set_carrier(&device, 2400000000ULL) < 0);
    assert(strstr(device.error, "requires reconfiguration"));
    assert(fake.registers[RADAR_REG_ENABLE] == 0);
    fake_init(&fake, &device);
    fake.ignore_write_at = 2; /* Driver accepts a write but readback disagrees. */
    assert(radar_set_gain(&device, false, 30) < 0);
    assert(strstr(device.error, "previous setting restored"));
    assert(!strcmp(fake_value(&fake, "in_voltage0_gain_control_mode"), "slow_attack"));

    fake_init(&fake, &device);
    fake.ignore_write_at = 2;
    assert(radar_set_carrier(&device, 2400000000ULL) < 0);
    assert(strstr(device.error, "previous frequency restored"));
    assert(fake.registers[RADAR_REG_ENABLE] == 0);
    assert(!strcmp(fake_value(&fake, "out_altvoltage0_RX_LO_frequency"), "2380000000"));

    fake_init(&fake, &device);
    strcpy(fake.values[8], "[-89.750000]"); /* Older driver's TX limits attribute. */
    assert(radar_set_gain(&device, true, -.2) == RADAR_INVALID);
    assert(!radar_set_gain(&device, true, -35.25));
    strcpy(fake.values[8], "[-89.75 0.25 0 garbage");
    assert(radar_set_gain(&device, true, -30) < 0);
    assert(strstr(device.error, "Cannot read gain limits"));

    puts("PASS: mute without IIO, timeouts, scene validation, signed phase, gain/carrier rollback");
}
