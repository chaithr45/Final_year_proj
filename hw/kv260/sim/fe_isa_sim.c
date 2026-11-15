/* Instruction-level simulator of the fabric feature engine (src/hw/fe_engine.py, rtl/fe_engine.v).
 * Executes the ROM program on whole recordings, one event per sample and per second, and returns the 38 classifier
 * features of every window; also counts instructions and the largest magnitude the 48-bit datapath must hold.
 * Build: gcc -O2 -shared -fPIC -o libfe_isa.so fe_isa_sim.c
 */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

enum { HALT = 0, LD = 1, ADD = 2, ST = 3, ASR = 4, ABS = 5, SAT = 6, LOG2 = 7, MAX = 8, J = 10, BR = 11, LDX = 12,
       ADDABS = 13 };

typedef struct {
    int64_t ram[1024];
    uint32_t rom[4096];
    int64_t A;
    int X;
    uint64_t instr;
    int64_t maxabs;
    int bad_op;
} fe_t;

static inline int64_t asr64(int64_t x, int s) { return x >= 0 ? (x >> s) : -(((-x) - 1) >> s) - 1; }
static inline int64_t ilog2_fx(int64_t v) {
    if (v <= 0) return 0;
    int p = 63 - __builtin_clzll((unsigned long long)v);
    int64_t mant = p >= 3 ? (v >> (p - 3)) : (v << (3 - p));
    return ((int64_t)p << 3) + (mant & 7);
}

static void run(fe_t *f, int pc) {
    for (;;) {
        uint32_t w = f->rom[pc++];
        int op = w >> 27, cond = (w >> 24) & 7, neg = (w >> 23) & 1, idx = (w >> 22) & 1, sh = (w >> 16) & 63;
        int addr = w & 0xFFFF, ea = (addr + (idx ? f->X : 0)) & 1023;
        int64_t v, A = f->A;
        f->instr++;
        switch (op) {
        case HALT: return;
        case LD: v = f->ram[ea] * ((int64_t)1 << sh); A = neg ? -v : v; break;
        case ADD: v = f->ram[ea] * ((int64_t)1 << sh); A += neg ? -v : v; break;
        case ST: f->ram[ea] = A; break;
        case ASR: A = asr64(A, sh); break;
        case ABS: A = A < 0 ? -A : A; break;
        case SAT: if (A > 524287) A = 524287; else if (A < -524288) A = -524288; break;
        case LOG2: A = ilog2_fx(A); break;
        case MAX: if (f->ram[ea] > A) A = f->ram[ea]; break;
        case J: pc = addr; break;
        case BR: {
            int t = 0;
            switch (cond) { case 0: t = A < 0; break; case 1: t = A >= 0; break; case 2: t = A == 0; break;
                            case 3: t = A != 0; break; case 4: t = A > 0; break; case 5: t = A <= 0; break; }
            if (t) pc = addr;
            break;
        }
        case LDX: f->X = (int)(f->ram[ea] & 1023); break;
        case ADDABS: v = f->ram[ea]; A += v < 0 ? -v : v; break;
        default: f->bad_op++; return;
        }
        f->A = A;
        int64_t m = A < 0 ? -A : A;
        if (m > f->maxabs) f->maxabs = m;
        if (op == LD || op == ADD) { int64_t mv = v < 0 ? -v : v; if (mv > f->maxabs) f->maxabs = mv; }
    }
}

fe_t *fe_new(const uint32_t *rom, int n_rom, const int64_t *ram, int n_ram) {
    fe_t *f = calloc(1, sizeof(fe_t));
    memcpy(f->rom, rom, sizeof(uint32_t) * n_rom);
    memcpy(f->ram, ram, sizeof(int64_t) * n_ram);
    return f;
}
void fe_free(fe_t *f) { free(f); }

/* io: addresses of IN_EEG1, IN_EEG2, IN_ECG, IN_EMG, IN_AX, IN_AY, IN_AZ, IN_GX, IN_GY, IN_GZ, PRES_ECG, PRES_EMG,
 *     PRES_ACC, PRES_GYR, WIN_VALID, WIN_INDEX, FEAT_0; entry: BIO, MOV, SEC, FLUSH.
 * Signals may be NULL (absent sensor). Returns the number of windows written to out (n_win_max x nf). */
int fe_run_recording(fe_t *f, const int *io, const int *entry, int nf, int n_sec,
                     const int16_t *eeg1, const int16_t *eeg2, const int16_t *ecg, const int16_t *emg,
                     const int16_t *ax, const int16_t *ay, const int16_t *az,
                     const int16_t *gx, const int16_t *gy, const int16_t *gz,
                     int16_t *out, int n_win_max, uint64_t *instr_per_event) {
    f->ram[io[10]] = ecg != NULL; f->ram[io[11]] = emg != NULL;
    f->ram[io[12]] = ax && ay && az; f->ram[io[13]] = gx && gy && gz;
    int n_out = 0;
    for (int b = 0; b < n_sec; b++) {
        for (int i = 0; i < 256; i++) {
            int64_t k = (int64_t)b * 256 + i;
            f->ram[io[0]] = eeg1[k]; f->ram[io[1]] = eeg2[k];
            f->ram[io[2]] = ecg ? ecg[k] : 0; f->ram[io[3]] = emg ? emg[k] : 0;
            uint64_t s0 = f->instr;
            run(f, entry[0]);
            instr_per_event[0] += f->instr - s0;
        }
        for (int i = 0; i < 25; i++) {
            int64_t k = (int64_t)b * 25 + i;
            f->ram[io[4]] = ax ? ax[k] : 0; f->ram[io[5]] = ay ? ay[k] : 0; f->ram[io[6]] = az ? az[k] : 0;
            f->ram[io[7]] = gx ? gx[k] : 0; f->ram[io[8]] = gy ? gy[k] : 0; f->ram[io[9]] = gz ? gz[k] : 0;
            uint64_t s0 = f->instr;
            run(f, entry[1]);
            instr_per_event[1] += f->instr - s0;
        }
        uint64_t s0 = f->instr;
        run(f, entry[2]);
        instr_per_event[2] += f->instr - s0;
        if (f->ram[io[14]]) {
            int w = (int)f->ram[io[15]];
            if (w >= 0 && w < n_win_max) {
                for (int j = 0; j < nf; j++) out[(int64_t)w * nf + j] = (int16_t)f->ram[io[16] + j];
                if (w + 1 > n_out) n_out = w + 1;
            }
        }
    }
    run(f, entry[3]);
    if (f->ram[io[14]]) {
        int w = (int)f->ram[io[15]];
        if (w >= 0 && w < n_win_max) {
            for (int j = 0; j < nf; j++) out[(int64_t)w * nf + j] = (int16_t)f->ram[io[16] + j];
            if (w + 1 > n_out) n_out = w + 1;
        }
    }
    return n_out;
}

uint64_t fe_instr(fe_t *f) { return f->instr; }
int64_t fe_maxabs(fe_t *f) { return f->maxabs; }
int fe_bad_op(fe_t *f) { return f->bad_op; }
