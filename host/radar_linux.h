#ifndef RADAR_LINUX_H
#define RADAR_LINUX_H
#include "radar_control.h"

typedef struct {
    int lock_fd;
    int memory_fd;
    volatile uint32_t *registers;
    char phy_path[256];
} radar_linux;

int radar_linux_open(radar_device *device, radar_linux *backend);
void radar_linux_close(radar_linux *backend);
#endif
