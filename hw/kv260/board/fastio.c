/* Fast register streaming for the SeizeLUT core on the KV260 (compiled on the board by seizelut_kv260.py):
 *   gcc -O2 -shared -fPIC -o libfastio.so fastio.c
 * Maps the core's AXI4-Lite window from /dev/mem and, per window, writes the feature words, writes COMMIT
 * (artefact flags) and polls RESULT until its result counter advances. Returns 0, or -(index + 1) of the
 * first window whose result did not arrive. Register offsets must match seizelut_regs.json.
 * sl_fe_run (core version 3): raw samples through the feature engine in the fabric, see below. */
#include <fcntl.h>
#include <stdint.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define REG_COMMIT 0x010u
#define REG_RESULT 0x014u
#define REG_FEAT0 0x100u
#define REG_FE_CTRL 0x0E4u
#define REG_FE_STATUS 0x0E8u
#define REG_FE_LASTWIN 0x0FCu
#define FE_WIN 0x1000u

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

/* Testing without a board: use p (any memory standing in for the register window) instead of /dev/mem. */
void sl_attach(void *p, uint32_t size) {
    base = (volatile uint32_t *)p;
    map_size = 0;
    (void)size;
}

void sl_close(void) {
    if (base && map_size) munmap((void *)base, map_size);
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

/* Wait until event number nev (16-bit count in FE_STATUS[31:16]) has started and the core is idle again
 * (FE_STATUS[0] = 0: engine, feature transfer and the classification it triggered). */
static int fe_wait(uint32_t nev, uint32_t *st_out) {
    long polls = 0;
    uint32_t st;
    do {
        st = base[REG_FE_STATUS >> 2];
        if (++polls > 50000000L) return -1;
    } while (((st >> 16) != (nev & 0xFFFFu)) || (st & 1u));
    *st_out = st;
    return 0;
}

/* Raw samples of one recording through the feature engine and the classifier, both in the fabric. The caller has
 * reset the classifier, restored the engine's register file and set the presence registers. Channels: eeg1, eeg2,
 * ecg, emg (256 Hz) and acc_x..gyr_z (25 Hz); NULL = absent (not written; the engine ignores it). io[10]: engine
 * register indices of IN_EEG1, IN_EEG2, IN_ECG, IN_EMG, IN_AX, IN_AY, IN_AZ, IN_GX, IN_GY, IN_GZ. Per second:
 * 256 x (inputs, BIO), 25 x (inputs, MOV), SEC; after the last second FLUSH. For every window that ends, win[k] =
 * its index, res[k] = RESULT, featw[k * nw ..] = the feature registers the engine filled. seconds[0] = wall time,
 * seconds[1] = slowest second; *last_status = the final FE_STATUS. Returns the number of windows, or -(second + 1)
 * on a timeout or when more than max_win windows end. */
int sl_fe_run(const int16_t *e1, const int16_t *e2, const int16_t *ecg, const int16_t *emg, const int16_t *ax,
              const int16_t *ay, const int16_t *az, const int16_t *gx, const int16_t *gy, const int16_t *gz,
              const uint32_t *io, int n_sec, int nw, int max_win, uint32_t *win, uint32_t *res, uint32_t *featw,
              double *seconds, uint32_t *last_status) {
    volatile uint32_t *fe = base + (FE_WIN >> 2);
    const int16_t *bio[4] = {e1, e2, ecg, emg};
    const int16_t *mov[6] = {ax, ay, az, gx, gy, gz};
    uint32_t nev = base[REG_FE_STATUS >> 2] >> 16, st = 0;
    int nwin = 0;
    double t0 = now(), worst = 0.0;
    for (int b = 0; b <= n_sec; b++) {
        double tb = now();
        if (b < n_sec) {
            for (int i = 0; i < 256; i++) {
                for (int c = 0; c < 4; c++)
                    if (bio[c]) fe[io[c]] = (uint32_t)(int32_t)bio[c][(size_t)b * 256 + i];
                base[REG_FE_CTRL >> 2] = 0u;
                if (fe_wait(++nev, &st)) return -(b + 1);
            }
            for (int i = 0; i < 25; i++) {
                for (int c = 0; c < 6; c++)
                    if (mov[c]) fe[io[4 + c]] = (uint32_t)(int32_t)mov[c][(size_t)b * 25 + i];
                base[REG_FE_CTRL >> 2] = 1u;
                if (fe_wait(++nev, &st)) return -(b + 1);
            }
            base[REG_FE_CTRL >> 2] = 2u;
        } else {
            base[REG_FE_CTRL >> 2] = 3u;          /* FLUSH: the last window */
        }
        if (fe_wait(++nev, &st)) return -(b + 1);
        if ((st >> 1) & 1u) {
            if (nwin >= max_win) return -(b + 1);
            win[nwin] = base[REG_FE_LASTWIN >> 2];
            res[nwin] = base[REG_RESULT >> 2];
            for (int k = 0; k < nw; k++) featw[(size_t)nwin * nw + k] = base[(REG_FEAT0 >> 2) + k];
            nwin++;
        }
        double dt = now() - tb;
        if (dt > worst) worst = dt;
    }
    seconds[0] = now() - t0;
    seconds[1] = worst;
    *last_status = st;
    return nwin;
}
