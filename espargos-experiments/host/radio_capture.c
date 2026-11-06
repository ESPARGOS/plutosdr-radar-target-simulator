/* Lab-only ADC observation through the otherwise unused ADI receive DMA.
 * Uses the existing no-map Maia spectrometer reservation, never Linux RAM.
 * No sample processing or buffering is added to the radar RF path.
 */
#define _DEFAULT_SOURCE
#include <fcntl.h>
#include <math.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#define BUFFER 0x1a000000u
static volatile sig_atomic_t stopped;
static void stop(int sig) {
    (void)sig;
    stopped = 1;
}
static uint32_t be32(const unsigned char *b) {
    return (uint32_t)b[0] << 24 | (uint32_t)b[1] << 16 | (uint32_t)b[2] << 8 | b[3];
}
int main(int argc, char **argv) {
    unsigned samples = 65536u;
    if (argc > 2) {
        fprintf(stderr, "Usage: radio-capture [65536|262144|1048576]\n");
        return 1;
    }
    if (argc == 2) {
        if (!strcmp(argv[1], "65536"))
            samples = 65536u;
        else if (!strcmp(argv[1], "262144"))
            samples = 262144u;
        else if (!strcmp(argv[1], "1048576"))
            samples = 1048576u;
        else {
            fprintf(stderr, "Unsupported sample count\n");
            return 1;
        }
    }
    const unsigned length = samples * 4u;
    unsigned char reg[8];
    char status[32] = {0};
    FILE *f = fopen("/proc/device-tree/reserved-memory/maia_sdr_spectrometer@1a000000/reg", "rb");
    if (!f || fread(reg, 1, 8, f) != 8) {
        fprintf(stderr, "Missing reserved DMA memory\n");
        return 1;
    }
    fclose(f);
    f = fopen("/proc/device-tree/maia-sdr-spectrometer/status", "rb");
    if (!f) {
        fprintf(stderr, "Cannot verify unused memory owner\n");
        return 1;
    }
    size_t n = fread(status, 1, sizeof(status) - 1, f);
    fclose(f);
    (void)n;
    if (be32(reg) != BUFFER || be32(reg + 4) < length || strcmp(status, "disabled")) {
        fprintf(stderr, "Memory is not the disabled Maia no-map reservation\n");
        return 1;
    }
    if (access("/proc/device-tree/reserved-memory/maia_sdr_spectrometer@1a000000/no-map", F_OK))
        return 1;
    int fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0) {
        perror("devmem");
        return 1;
    }
    volatile uint32_t *dma = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0x7c400000);
    if (dma == MAP_FAILED) {
        perror("dma mmap");
        close(fd);
        return 1;
    }
    if (dma[3] != 0x444d4143 || ((dma[4] >> 12) & 3) != 2 || ((dma[4] >> 4) & 3) != 0 ||
        dma[0x400 / 4]) {
        fprintf(stderr, "Wrong or already active receive DMA\n");
        munmap((void *)dma, 4096);
        close(fd);
        return 1;
    }
    uint16_t *memory = mmap(NULL, length, PROT_READ | PROT_WRITE, MAP_SHARED, fd, BUFFER);
    if (memory == MAP_FAILED) {
        perror("reserved mmap");
        munmap((void *)dma, 4096);
        close(fd);
        return 1;
    }
    const unsigned offsets[] = {0x80, 0x40c, 0x410, 0x418, 0x41c, 0x420};
    uint32_t saved[6];
    for (unsigned i = 0; i < 6; i++)
        saved[i] = dma[offsets[i] / 4];
    signal(SIGINT, stop);
    signal(SIGTERM, stop);
    dma[0x80 / 4] = 3;
    dma[0x84 / 4] = 3;
    dma[0x400 / 4] = 1;
    dma[0x40c / 4] = 0;
    dma[0x410 / 4] = BUFFER;
    dma[0x418 / 4] = length - 1;
    dma[0x41c / 4] = 0;
    dma[0x420 / 4] = 0;
    __sync_synchronize();
    unsigned id = dma[0x404 / 4];
    int ok = 0;
    if (id < 32 && dma[0x408 / 4] == 0) {
        dma[0x408 / 4] = 1;
        __sync_synchronize();
        for (unsigned tries = 0; tries < 3000 && !stopped; tries++) {
            if (!dma[0x408 / 4] && (dma[0x428 / 4] & (1u << id))) {
                ok = 1;
                break;
            }
            usleep(1000);
        }
    }
    dma[0x400 / 4] = 0;
    __sync_synchronize();
    usleep(1000);
    dma[0x84 / 4] = 3;
    for (unsigned i = 1; i < 6; i++)
        dma[offsets[i] / 4] = saved[i];
    dma[0x80 / 4] = saved[0];
    __sync_synchronize();
    if (ok && !stopped) {
        unsigned peak[2] = {0}, rails[2] = {0};
        double power[2] = {0};
        for (unsigned i = 0; i < length / 2; i++) {
            int value = ((memory[i] & 4095) ^ 2048) - 2048;
            unsigned magnitude = (unsigned)abs(value), ch = i & 1;
            if (magnitude > peak[ch])
                peak[ch] = magnitude;
            if (magnitude >= 2047)
                rails[ch]++;
            power[ch] += (double)value * value;
        }
        fprintf(stderr,
                "{\"samples\":%u,\"peak_i\":%u,\"peak_q\":%u,\"rail_i\":%u,\"rail_q\":%u,\"rms_i\":"
                "%.4f,\"rms_q\":%.4f}\n",
                samples, peak[0], peak[1], rails[0], rails[1], sqrt(power[0] / samples),
                sqrt(power[1] / samples));
        ok = fwrite(memory, 1, length, stdout) == length;
    } else {
        fprintf(stderr, "ADC DMA timeout or interruption; DMA disabled\n");
        ok = 0;
    }
    munmap(memory, length);
    munmap((void *)dma, 4096);
    close(fd);
    return ok ? 0 : 1;
}
