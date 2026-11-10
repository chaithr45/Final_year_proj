/* Fast register streaming for the SeizeLUT core on the KV260 (compiled on the board by seizelut_kv260.py):
 *   gcc -O2 -shared -fPIC -o libfastio.so fastio.c
 * Maps the core's AXI4-Lite window from /dev/mem and, per window, writes the feature words, writes COMMIT
 * (artefact flags) and polls RESULT until its result counter advances. Returns 0, or -(index + 1) of the
 * first window whose result did not arrive. Register offsets must match seizelut_regs.json. */
#include <fcntl.h>
#include <stdint.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define REG_COMMIT 0x010u
#define REG_RESULT 0x014u
#define REG_FEAT0 0x100u

static volatile uint32_t *base = 0;
static size_t map_size = 0;

int sl_open(uint64_t phys, uint32_t size) {
    int fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0) return -1;
    void *p = mmap(0, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, (off_t)phys);
    close(fd);
    if (p == MAP_FAILED) return -2;
    base = (volatile uint32_t *)p;
    map_size = size;
    return 0;
}

void sl_close(void) {
    if (base) munmap((void *)base, map_size);
    base = 0;
}

uint32_t sl_read(uint32_t off) { return base[off >> 2]; }
void sl_write(uint32_t off, uint32_t v) { base[off >> 2] = v; }

static double now(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + 1e-9 * ts.tv_nsec;
}

/* words: n x nw feature words (row-major), art: n artefact codes, results: n RESULT words.
 * seconds[0] = wall time of the whole run, seconds[1] = slowest single window. */
int sl_run(const uint32_t *words, const uint8_t *art, int n, int nw, uint32_t *results, double *seconds) {
    uint32_t seq = base[REG_RESULT >> 2] >> 16;
    double t0 = now(), worst = 0.0;
    for (int i = 0; i < n; i++) {
        double ti = now();
        const uint32_t *w = words + (size_t)i * nw;
        for (int k = 0; k < nw; k++) base[(REG_FEAT0 >> 2) + k] = w[k];
        base[REG_COMMIT >> 2] = art[i];
        seq = (seq + 1u) & 0xFFFFu;
        uint32_t r = 0;
        long polls = 0;
        do {
            r = base[REG_RESULT >> 2];
            if (++polls > 1000000L) return -(i + 1);
        } while (!((r >> 15) & 1u) || ((r >> 16) != seq));
        results[i] = r;
        double dt = now() - ti;
        if (dt > worst) worst = dt;
    }
    seconds[0] = now() - t0;
    seconds[1] = worst;
    return 0;
}
