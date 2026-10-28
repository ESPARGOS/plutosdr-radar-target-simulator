#define _DEFAULT_SOURCE
#include "radar_linux.h"
#include <errno.h>
#include <fcntl.h>
#include <glob.h>
#include <stdio.h>
#include <string.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <unistd.h>

static uint32_t read_register(void *context, unsigned index) {
    radar_linux *backend = context;
    __sync_synchronize();
    return backend->registers[index];
}

static void write_register(void *context, unsigned index, uint32_t value) {
    radar_linux *backend = context;
    __sync_synchronize();
    backend->registers[index] = value;
    __sync_synchronize();
}

static int find_phy(radar_linux *backend) {
    if (backend->phy_path[0])
        return 0;
    glob_t paths;
    if (glob("/sys/bus/iio/devices/iio:device*/name", 0, NULL, &paths))
        return -1;
    int found = -1;
    for (size_t i = 0; i < paths.gl_pathc; ++i) {
        FILE *file = fopen(paths.gl_pathv[i], "r");
        char name[64];
        if (!file)
            continue;
        bool match = false;
        if (fgets(name, sizeof(name), file)) {
            name[strcspn(name, "\r\n")] = 0;
            match = !strcmp(name, "ad9361-phy");
        }
        fclose(file);
        if (match) {
            snprintf(backend->phy_path, sizeof(backend->phy_path), "%s", paths.gl_pathv[i]);
            *strrchr(backend->phy_path, '/') = 0;
            found = 0;
            break;
        }
    }
    globfree(&paths);
    return found;
}

static int attribute_path(radar_linux *backend, const char *name, char *path, size_t size) {
    if (find_phy(backend))
        return -1;
    int count = snprintf(path, size, "%s/%s", backend->phy_path, name);
    return count < 0 || (size_t)count >= size ? -1 : 0;
}

static int read_attribute(void *context, const char *name, char *value, size_t size) {
    char path[384];
    if (attribute_path(context, name, path, sizeof(path)))
        return -1;
    FILE *file = fopen(path, "r");
    if (!file)
        return -1;
    int result = fgets(value, size, file) ? 0 : -1;
    if (!result)
        value[strcspn(value, "\r\n")] = 0;
    fclose(file);
    return result;
}

static int write_attribute(void *context, const char *name, const char *value) {
    char path[384];
    if (attribute_path(context, name, path, sizeof(path)))
        return -1;
    int fd = open(path, O_WRONLY | O_CLOEXEC);
    if (fd < 0)
        return -1;
    size_t length = strlen(value);
    ssize_t count;
    do {
        count = write(fd, value, length);
    } while (count < 0 && errno == EINTR);
    int result = count == (ssize_t)length ? 0 : -1;
    close(fd);
    return result;
}

static void sleep_ms(void *context, unsigned milliseconds) {
    (void)context;
    usleep(milliseconds * 1000);
}

static const radar_io linux_io = {read_register, write_register, read_attribute, write_attribute,
                                  sleep_ms};

void radar_linux_close(radar_linux *backend) {
    if (backend->registers)
        munmap((void *)backend->registers, RADAR_MAP_SIZE);
    if (backend->memory_fd >= 0)
        close(backend->memory_fd);
    if (backend->lock_fd >= 0)
        close(backend->lock_fd);
    *backend = (radar_linux){.lock_fd = -1, .memory_fd = -1};
}

int radar_linux_open(radar_device *device, radar_linux *backend) {
    *backend = (radar_linux){.lock_fd = -1, .memory_fd = -1};
    *device = (radar_device){.io = &linux_io, .context = backend};
    backend->lock_fd = open("/tmp/radar-control.lock", O_CREAT | O_RDWR | O_CLOEXEC, 0600);
    if (backend->lock_fd < 0) {
        device->error = "Control lock unavailable";
        goto failed;
    }
    bool locked = false;
    for (unsigned attempt = 0; attempt < 1000; ++attempt) {
        if (!flock(backend->lock_fd, LOCK_EX | LOCK_NB)) {
            locked = true;
            break;
        }
        if (errno != EWOULDBLOCK && errno != EINTR)
            break;
        usleep(5000);
    }
    if (!locked) {
        device->error = "Control lock timed out";
        goto failed;
    }
    backend->memory_fd = open("/dev/mem", O_RDWR | O_SYNC | O_CLOEXEC);
    if (backend->memory_fd < 0) {
        device->error = "FPGA access unavailable";
        goto failed;
    }
    void *mapping = mmap(NULL, RADAR_MAP_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED,
                         backend->memory_fd, RADAR_BASE);
    if (mapping == MAP_FAILED) {
        device->error = "FPGA mapping failed";
        goto failed;
    }
    backend->registers = mapping;
    if (radar_check(device))
        goto failed;
    return 0;
failed:
    radar_linux_close(backend);
    return -1;
}
