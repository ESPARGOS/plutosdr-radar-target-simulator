#include "fake_device.h"
#include <stdio.h>
#include <string.h>

static const char *names[] = {"in_voltage_sampling_frequency",
                              "out_altvoltage0_RX_LO_frequency",
                              "out_altvoltage1_TX_LO_frequency",
                              "in_voltage_rf_bandwidth",
                              "out_voltage_rf_bandwidth",
                              "in_voltage0_hardwaregain",
                              "out_voltage0_hardwaregain",
                              "in_voltage0_hardwaregain_available",
                              "out_voltage0_hardwaregain_available",
                              "in_voltage0_gain_control_mode",
                              "in_out_voltage_filter_fir_en"};
static int index_of(const char *name) {
    for (unsigned i = 0; i < sizeof(names) / sizeof(names[0]); ++i)
        if (!strcmp(name, names[i]))
            return (int)i;
    return -1;
}
const char *fake_value(fake_device *fake, const char *name) {
    int index = index_of(name);
    return index >= 0 ? fake->values[index] : "";
}
static uint32_t read_register(void *context, unsigned index) {
    fake_device *fake = context;
    if (index == RADAR_REG_STATUS && fake->stuck)
        return 1;
    return fake->registers[index];
}
static void write_register(void *context, unsigned index, uint32_t value) {
    fake_device *fake = context;
    ++fake->register_writes;
    fake->registers[index] = value;
}
static int read_attribute(void *context, const char *name, char *value, size_t size) {
    fake_device *fake = context;
    ++fake->attribute_reads;
    int index = index_of(name);
    if (fake->missing_radio || index < 0 || (fake->fail_read && !strcmp(fake->fail_read, name)))
        return -1;
    snprintf(value, size, "%s", fake->values[index]);
    return 0;
}
static int write_attribute(void *context, const char *name, const char *value) {
    fake_device *fake = context;
    ++fake->attribute_writes;
    int index = index_of(name);
    if (fake->missing_radio || index < 0)
        return -1;
    if (fake->fail_write_at &&
        (fake->attribute_writes == fake->fail_write_at ||
         (fake->fail_rollback && fake->attribute_writes > fake->fail_write_at)))
        return -1;
    if (fake->attribute_writes != fake->ignore_write_at)
        snprintf(fake->values[index], sizeof(fake->values[index]), "%s", value);
    return 0;
}
static void sleep_ms(void *context, unsigned milliseconds) {
    fake_device *fake = context;
    fake->sleeps += milliseconds;
}
static const radar_io io = {read_register, write_register, read_attribute, write_attribute,
                            sleep_ms};
void fake_init(fake_device *fake, radar_device *device) {
    memset(fake, 0, sizeof(*fake));
    *device = (radar_device){.io = &io, .context = fake};
    fake->registers[RADAR_REG_SIGNATURE] = RADAR_SIGNATURE;
    fake->registers[RADAR_REG_VERSION] = 0x10010;
    fake->registers[RADAR_REG_ENABLE] = 15;
    for (unsigned i = 0; i < RADAR_TARGETS; ++i) {
        fake->registers[RADAR_REG_TARGET_BASE + 4 * i] = i * 80;
        fake->registers[RADAR_REG_TARGET_BASE + 4 * i + 2] = 4096;
    }
    const char *defaults[] = {"159999999",       "2380000000",  "2380000000", "20000000",
                              "20000000",        "35",          "-25",        "[-3 1 71]",
                              "[-89.75 0.25 0]", "slow_attack", "0"};
    for (unsigned i = 0; i < sizeof(defaults) / sizeof(defaults[0]); ++i)
        snprintf(fake->values[i], sizeof(fake->values[i]), "%s", defaults[i]);
}
