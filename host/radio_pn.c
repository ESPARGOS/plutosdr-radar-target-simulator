// Check RX with a PRBS pattern and TX through digital loopback at startup.
// Restore the FPGA test registers afterward and leave TX attenuated.
#define _DEFAULT_SOURCE
#include "radar_control.h"
#include "radar_linux.h"
#include <fcntl.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
static volatile sig_atomic_t interrupted;
static void stop_test(int signum) {
    (void)signum;
    interrupted = 1;
}
static char phy[256], debug[256];
static int attr(const char *base, const char *name, const char *value) {
    char path[512];
    snprintf(path, sizeof path, "%s/%s", base, name);
    int fd = open(path, O_WRONLY);
    if (fd < 0) {
        perror(path);
        return -1;
    }
    size_t n = strlen(value);
    int ok = write(fd, value, n) == (ssize_t)n;
    close(fd);
    return ok ? 0 : -1;
}
static int readattr(const char *base, const char *name, char *value, size_t size) {
    char path[512];
    snprintf(path, sizeof path, "%s/%s", base, name);
    FILE *f = fopen(path, "r");
    if (!f)
        return -1;
    int ok = fgets(value, (int)size, f) != NULL;
    fclose(f);
    return ok ? 0 : -1;
}
static int regread(unsigned reg) {
    char value[64];
    snprintf(value, sizeof value, "0x%x", reg);
    if (attr(debug, "direct_reg_access", value) ||
        readattr(debug, "direct_reg_access", value, sizeof value))
        return -1;
    return (int)strtoul(value, NULL, 0);
}
static int regwrite(unsigned reg, unsigned value) {
    char text[64];
    snprintf(text, sizeof text, "0x%x 0x%x", reg, value);
    return attr(debug, "direct_reg_access", text);
}
/* Sweep actual clock/data pairs. The driver's short scan can miss a valid
 * pair at high CMOS rates. Select a passing point farthest from failing taps,
 * then let the normal sustained PN test qualify it without clearing errors. */
static int tune_port(volatile uint32_t *rx, unsigned port, unsigned seconds) {
    unsigned char good[16][16] = {{0}};
    for (unsigned clock = 0; clock < 16; ++clock) {
        if (attr(phy, "ensm_mode", "alert") || regwrite(port, clock << 4) ||
            attr(phy, "ensm_mode", "fdd"))
            return -1;
        usleep(20000);
        printf("%s clock %x: ", port == 6 ? "RX" : "TX", clock);
        for (unsigned data = 0; data < 16; ++data) {
            if (interrupted || regwrite(port, clock << 4 | data))
                return -1;
            usleep(5000);
            rx[0x404 / 4] = 7;
            rx[0x444 / 4] = 7;
            usleep(10000);
            good[clock][data] = !((rx[0x404 / 4] | rx[0x444 / 4]) & 6) && (rx[0x5c / 4] & 1);
            printf("%c", good[clock][data] ? 'o' : '.');
        }
        puts("");
        fflush(stdout);
    }
    /* Prefer delaying RX data to moving DATA_CLK and relocking the MMCM.
       Fall back to the full grid if no data-only point passes qualification. */
    for (unsigned attempt = 0; attempt < 256 && !interrupted; ++attempt) {
        bool data_only = false;
        if (port == 6)
            for (unsigned data = 0; data < 16; ++data)
                data_only |= good[0][data];
        int best = -1, margin = -1, center_distance = 10000;
        for (int clock = 0; clock < 16; ++clock)
            for (int data = 0; data < 16; ++data) {
                if (!good[clock][data] || (data_only && clock))
                    continue;
                int distance = data_only ? 16 : clock + 1;
                if (data + 1 < distance)
                    distance = data + 1;
                if (!data_only && 16 - clock < distance)
                    distance = 16 - clock;
                if (16 - data < distance)
                    distance = 16 - data;
                for (int c = 0; c < 16; ++c)
                    for (int d = 0; d < 16; ++d) {
                        if ((data_only && c) || good[c][d])
                            continue;
                        int dc = abs(c - clock), dd = abs(d - data), dist = dc > dd ? dc : dd;
                        if (dist < distance)
                            distance = dist;
                    }
                int center =
                    (2 * clock - 15) * (2 * clock - 15) + (2 * data - 15) * (2 * data - 15);
                if (distance > margin || (distance == margin && center < center_distance)) {
                    center_distance = center;
                    margin = distance;
                    best = clock * 16 + data;
                }
            }
        if (best < 0)
            return -1;
        if (attr(phy, "ensm_mode", "alert") || regwrite(port, best) ||
            attr(phy, "ensm_mode", "fdd"))
            return -1;
        usleep(100000);
        rx[0x404 / 4] = 7;
        rx[0x444 / 4] = 7;
        bool passed = true;
        for (unsigned sample = 0; sample < seconds * 10 && !interrupted; ++sample) {
            usleep(100000);
            if (((rx[0x404 / 4] | rx[0x444 / 4]) & 6) || !(rx[0x5c / 4] & 1)) {
                passed = false;
                break;
            }
        }
        if (interrupted)
            return -1;
        printf("%s candidate 0x%02x: %s (%u-second qualification)\n", port == 6 ? "RX" : "TX", best,
               passed ? "passed" : "rejected", seconds);
        fflush(stdout);
        if (passed)
            return 0;
        good[best >> 4][best & 15] = 0;
    }
    return -1;
}
/* Keep data and frame delay coherent. Select the middle of the common RX
 * eye, then independently qualify TX loopback with this receive setting. */
static int tune_rx_inputs(volatile uint32_t *rx) {
    unsigned best_start = 0, best_width = 0, start = 0, width = 0;
    for (unsigned tap = 0; tap < 32 && !interrupted; ++tap) {
        for (unsigned lane = 0; lane < 13; ++lane)
            rx[(0x800 + lane * 4) / 4] = tap;
        usleep(10000);
        rx[0x404 / 4] = 7;
        rx[0x444 / 4] = 7;
        usleep(50000);
        bool good = !((rx[0x404 / 4] | rx[0x444 / 4]) & 6) && (rx[0x5c / 4] & 1);
        if (good) {
            if (!width)
                start = tap;
            ++width;
            if (width > best_width) {
                best_start = start;
                best_width = width;
            }
        } else
            width = 0;
    }
    if (interrupted || best_width < 2) {
        fprintf(stderr, "RX inputs have insufficient common timing margin (%u taps)\n", best_width);
        return -1;
    }
    unsigned selected = best_start + (best_width - 1) / 2;
    for (unsigned lane = 0; lane < 13; ++lane)
        rx[(0x800 + lane * 4) / 4] = selected;
    usleep(100000);
    printf("RX inputs: %u clean taps from %u, selected %u\n", best_width, best_start, selected);
    fflush(stdout);
    return 0;
}

int main(int argc, char **argv) {
    signal(SIGINT, stop_test);
    signal(SIGTERM, stop_test);
    if (argc > 3 || (argc == 3 && strcmp(argv[2], "--tune"))) {
        fputs("usage: radio-pn [seconds [--tune]]\n", stderr);
        return 2;
    }
    bool tune = argc == 3;
    unsigned seconds = argc > 1 ? (unsigned)strtoul(argv[1], NULL, 10) : 2;
    if (!seconds || seconds > 60) {
        fprintf(stderr, "duration must be 1..60 seconds\n");
        return 2;
    }
    for (int i = 0; i < 16; i++) {
        char name[64];
        snprintf(phy, sizeof phy, "/sys/bus/iio/devices/iio:device%d", i);
        if (!readattr(phy, "name", name, sizeof name) && !strncmp(name, "ad9361-phy", 10)) {
            snprintf(debug, sizeof debug, "/sys/kernel/debug/iio/iio:device%d", i);
            break;
        }
    }
    if (!debug[0] || attr(phy, "out_voltage0_hardwaregain", "-60"))
        return 2;
    int initial_rx_delay = regread(6), initial_tx_delay = regread(7);
    if (initial_rx_delay < 0 || initial_tx_delay < 0)
        return 2;
    printf("Interface delays: RX=0x%02x TX=0x%02x\n", initial_rx_delay, initial_tx_delay);
    char prbs[64], loop[64];
    if (readattr(debug, "bist_prbs", prbs, sizeof prbs) ||
        readattr(debug, "loopback", loop, sizeof loop))
        return 2;
    int fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0) {
        perror("/dev/mem");
        return 2;
    }
    volatile uint32_t *rx = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0x79020000);
    volatile uint32_t *tx = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0x79024000);
    if (rx == MAP_FAILED || tx == MAP_FAILED) {
        perror("mmap");
        close(fd);
        return 2;
    }
    unsigned ro[] = {0x400, 0x440, 0x418, 0x458}, to[] = {0x418, 0x458, 0x414, 0x454};
    uint32_t rs[4], ts[4], original_lanes[13];
    for (unsigned lane = 0; lane < 13; ++lane)
        original_lanes[lane] = rx[(0x800 + lane * 4) / 4];
    for (int i = 0; i < 4; i++) {
        rs[i] = rx[ro[i] / 4];
        ts[i] = tx[to[i] / 4];
    }
    radar_device radar;
    radar_linux backend;
    radar_scene original_scene;
    if (tune) {
        if (radar_linux_open(&radar, &backend)) {
            fprintf(stderr, "%s\n", radar.error);
            return 2;
        }
        radar_get_scene(&radar, &original_scene);
        radar_scene stress = {.mask = 15,
                              .targets = {{0, 0x12345678, 4096},
                                          {1, 0x23456789, 4096},
                                          {17, 0x89abcdef, 4096},
                                          {2047, 0x98765432, 4096}}};
        if (radar_apply(&radar, &stress)) {
            fprintf(stderr, "%s\n", radar.error);
            radar_linux_close(&backend);
            return 2;
        }
    }
    int failed = 0;
    for (int mode = 0; mode < 2 && !failed; mode++) {
        if (attr(debug, "bist_prbs", "0") || attr(debug, "loopback", mode ? "1" : "0")) {
            failed = 1;
            break;
        }
        rx[0x40 / 4] = 2;
        rx[0x40 / 4] = 3;
        tx[0x40 / 4] = 3;
        for (int ch = 0; ch < 2; ch++) {
            rx[(0x400 + 64 * ch) / 4] = 0x251;
            rx[(0x418 + 64 * ch) / 4] = mode ? 9 << 16 : 0;
            if (mode) {
                tx[(0x418 + 64 * ch) / 4] = 9;
                tx[(0x414 + 64 * ch) / 4] = 0;
            }
        }
        tx[0x44 / 4] = 1;
        if ((!mode && attr(debug, "bist_prbs", "2")) || attr(phy, "ensm_mode", "alert") ||
            attr(phy, "ensm_mode", "fdd")) {
            failed = 1;
            break;
        }
        usleep(100000);
        if (tune && (tune_port(rx, mode ? 7 : 6, seconds) || (!mode && tune_rx_inputs(rx)))) {
            failed = 1;
            break;
        }
        if (mode) {
            int selected = regread(7);
            if (selected < 0) {
                failed = 1;
                break;
            }
            for (int attempt = 0; attempt < 5; attempt++) {
                rx[0x404 / 4] = 7;
                rx[0x444 / 4] = 7;
                usleep(50000);
                printf("TX acquisition %d: status %u %u\n", attempt + 1, rx[0x404 / 4],
                       rx[0x444 / 4]);
                if (!((rx[0x404 / 4] | rx[0x444 / 4]) & 6))
                    break;
                if (attempt < 4) {
                    if (regwrite(7, selected ? 0 : 0xf0)) {
                        failed = 1;
                        break;
                    }
                    usleep(10000);
                    if (regwrite(7, (unsigned)selected)) {
                        failed = 1;
                        break;
                    }
                    usleep(50000);
                }
            }
        }
        if (failed)
            break;
        // Sticky checker errors are cleared once, never during the measured interval.
        rx[0x404 / 4] = 7;
        rx[0x444 / 4] = 7;
        for (unsigned i = 0; i < seconds * 10 && !interrupted; i++)
            usleep(100000);
        if (interrupted) {
            failed = 1;
            break;
        }
        uint32_t a = rx[0x404 / 4], b = rx[0x444 / 4], global = rx[0x5c / 4];
        printf("%s: status %u %u, global %u, %u seconds\n", mode ? "TX loopback" : "RX PN", a, b,
               global, seconds);
        failed |= ((a | b) & 6) != 0 || !(global & 1);
    }
    if (failed && tune) {
        for (unsigned lane = 0; lane < 13; ++lane)
            rx[(0x800 + lane * 4) / 4] = original_lanes[lane];
        failed |= attr(phy, "ensm_mode", "alert") != 0;
        failed |= regwrite(6, (unsigned)initial_rx_delay) != 0;
        failed |= regwrite(7, (unsigned)initial_tx_delay) != 0;
        failed |= attr(phy, "ensm_mode", "fdd") != 0;
    }
    failed |= attr(debug, "bist_prbs", prbs) != 0;
    failed |= attr(debug, "loopback", loop) != 0;
    for (int i = 0; i < 4; i++) {
        rx[ro[i] / 4] = rs[i];
        tx[to[i] / 4] = ts[i];
    }
    rx[0x40 / 4] = 2;
    rx[0x40 / 4] = 3;
    tx[0x44 / 4] = 1;
    if (tune) {
        if (failed)
            original_scene.mask = 0;
        failed |= radar_apply(&radar, &original_scene) != 0;
        radar_linux_close(&backend);
    }
    munmap((void *)rx, 4096);
    munmap((void *)tx, 4096);
    close(fd);
    return failed ? 1 : 0;
}
