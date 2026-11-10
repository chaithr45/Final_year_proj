/* SeizeLUT integer front end in C: a streaming, bit-exact port of src/features/golden.py (mode "int").
 *
 * Input:  int16 samples after the fixed-gain conversion (spec/fixed_point.md): two behind-the-ear EEG channels
 *         (256 Hz), optional ECG and EMG (256 Hz) and optional 3-axis accelerometer and gyroscope (25 Hz).
 * Output: per one-second window t (covering seconds [t, t+2)) the 117 integer features in spec order and the two
 *         EEG artefact flags. Arithmetic: int64, floor shifts, SPT biquads with second-order error feedback and
 *         20-bit saturation, integer log2 with 3 fractional bits; samples are processed in one pass, block by block,
 *         as an embedded implementation would (memory grows only with the number of windows).
 * Build:  gcc -O2 -shared -fPIC -o libseizelut_fe.so seizelut_fe.c      (library, used by frontend.py)
 *         gcc -O2 -DFE_MAIN -o seizelut_fe seizelut_fe.c                 (command line, see fe_main below)
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "seizelut_fe_params.h"

static inline int64_t asr(int64_t x, int s) { return x >= 0 ? (x >> s) : -(((-x) - 1) >> s) - 1; }  /* floor(x / 2^s) */
static inline int64_t shl(int64_t x, int s) { return x * ((int64_t)1 << s); }
static inline int64_t iabs(int64_t x) { return x < 0 ? -x : x; }

static inline int64_t ilog2_fx(int64_t v) {
    if (v <= 0) return 0;
    int p = 63 - __builtin_clzll((unsigned long long)v);
    int64_t mant = p >= LOG_FRAC ? (v >> (p - LOG_FRAC)) : (v << (LOG_FRAC - p));
    return ((int64_t)p << LOG_FRAC) + (mant & ((1 << LOG_FRAC) - 1));
}

/* ------------------------------------------------------------------------------------------- biquad */
typedef struct { int64_t x1, x2, y1, y2, e1, e2; } bq_t;

static inline int64_t bq(bq_t *s, const fe_coef *c, int64_t x0) {
    int64_t acc = c->b0 * x0 + c->b1 * s->x1 + c->b2 * s->x2 - c->a1 * s->y1 - c->a2 * s->y2 + 2 * s->e1 - s->e2;
    int64_t v = asr(acc, c->frac);
    s->e2 = s->e1;
    s->e1 = acc - shl(v, c->frac);
    const int64_t lim = ((int64_t)1 << (FILTER_STATE_BITS - 1)) - 1;
    if (v > lim) v = lim;
    else if (v < -lim - 1) v = -lim - 1;
    s->x2 = s->x1; s->x1 = x0; s->y2 = s->y1; s->y1 = v;
    return v;
}

/* ------------------------------------------------------------------------------------------- block statistics */
typedef struct { int64_t prev; int psign, last_slope, started; int64_t mav, ll, zc, ext; } bs_t;

static inline void bs_step(bs_t *b, int64_t v) {
    b->mav += iabs(v);
    if (!b->started) { b->prev = v; b->psign = v >= 0; b->last_slope = 0; b->started = 1; return; }
    int64_t d = v - b->prev;
    b->ll += iabs(d);
    int s = v >= 0;
    if (s != b->psign) b->zc++;
    b->psign = s;
    if (d != 0) {
        int sl = d > 0 ? 1 : -1;
        if (b->last_slope != 0 && sl != b->last_slope) b->ext++;
        b->last_slope = sl;
    }
    b->prev = v;
}
static inline void bs_clear(bs_t *b) { b->mav = b->ll = b->zc = b->ext = 0; }

#define WIN(a, t) ((a)[t] + (a)[(t) + 1])
#define X_(t, f) X[(int64_t)(t) * N_FEATURES + (f)]

/* ------------------------------------------------------------------------------------------- EEG */
enum { E_MAV, E_LL, E_ZC, E_EXT, E_DELTA, E_THETA, E_ALPHA, E_BETA, E_HF, E_BROAD, E_N };
static const int CH_FEAT[2][10] = {
    {F_eeg_ch1_mav, F_eeg_ch1_ll, F_eeg_ch1_mob, F_eeg_ch1_zc, F_eeg_ch1_ext, F_eeg_ch1_delta, F_eeg_ch1_theta,
     F_eeg_ch1_alpha, F_eeg_ch1_beta, F_eeg_ch1_hf},
    {F_eeg_ch2_mav, F_eeg_ch2_ll, F_eeg_ch2_mob, F_eeg_ch2_zc, F_eeg_ch2_ext, F_eeg_ch2_delta, F_eeg_ch2_theta,
     F_eeg_ch2_alpha, F_eeg_ch2_beta, F_eeg_ch2_hf}};
static const int CROSS_FEAT[10][3] = {
    {F_eeg_mav_mean, F_eeg_mav_max, F_eeg_mav_absdiff}, {F_eeg_ll_mean, F_eeg_ll_max, F_eeg_ll_absdiff},
    {F_eeg_mob_mean, F_eeg_mob_max, F_eeg_mob_absdiff}, {F_eeg_zc_mean, F_eeg_zc_max, F_eeg_zc_absdiff},
    {F_eeg_ext_mean, F_eeg_ext_max, F_eeg_ext_absdiff}, {F_eeg_delta_mean, F_eeg_delta_max, F_eeg_delta_absdiff},
    {F_eeg_theta_mean, F_eeg_theta_max, F_eeg_theta_absdiff}, {F_eeg_alpha_mean, F_eeg_alpha_max, F_eeg_alpha_absdiff},
    {F_eeg_beta_mean, F_eeg_beta_max, F_eeg_beta_absdiff}, {F_eeg_hf_mean, F_eeg_hf_max, F_eeg_hf_absdiff}};

static int eeg(int64_t n_win, const int16_t *x1, const int16_t *x2, int64_t n, int64_t *X, uint8_t *art) {
    int64_t nb = n / BLOCK_BIO;
    int64_t *blk = calloc((size_t)(nb > 0 ? nb : 1) * (2 * E_N + 1), sizeof(int64_t));
    if (!blk) return -1;
    const int16_t *xs[2] = {x1, x2};
    bq_t f[2][14];
    bs_t b[2];
    memset(f, 0, sizeof f);
    memset(b, 0, sizeof b);
    int64_t band[2][6] = {{0}}, agree = 0;
    for (int64_t i = 0; i < nb * BLOCK_BIO; i++) {
        int sg[2];
        for (int c = 0; c < 2; c++) {
            int64_t q = xs[c][i];
            bq_t *s = f[c];
            int64_t h1 = bq(&s[0], &C_eeg_hp1, q);
            int64_t xbp = bq(&s[1], &C_eeg_lp25, h1);
            int64_t de = bq(&s[2], &C_eeg_lp4, h1);
            int64_t th = bq(&s[4], &C_eeg_lp8, bq(&s[3], &C_eeg_hp4, q));
            int64_t al = bq(&s[6], &C_eeg_lp13, bq(&s[5], &C_eeg_hp8, q));
            int64_t be = bq(&s[8], &C_eeg_lp25, bq(&s[7], &C_eeg_hp13, q));
            int64_t hf = bq(&s[10], &C_eeg_lp60, bq(&s[9], &C_eeg_hp25, q));
            int64_t br = bq(&s[13], &C_eeg_notch50, bq(&s[12], &C_eeg_lp60, bq(&s[11], &C_eeg_hp05, q)));
            bs_step(&b[c], xbp);
            band[c][0] += iabs(de); band[c][1] += iabs(th); band[c][2] += iabs(al);
            band[c][3] += iabs(be); band[c][4] += iabs(hf); band[c][5] += iabs(br);
            sg[c] = xbp >= 0;
        }
        agree += (sg[0] == sg[1]);
        if ((i + 1) % BLOCK_BIO == 0) {
            int64_t k = i / BLOCK_BIO, *r = blk + k * (2 * E_N + 1);
            for (int c = 0; c < 2; c++) {
                int64_t *rc = r + c * E_N;
                rc[E_MAV] = b[c].mav; rc[E_LL] = b[c].ll; rc[E_ZC] = b[c].zc; rc[E_EXT] = b[c].ext;
                for (int j = 0; j < 6; j++) { rc[E_DELTA + j] = band[c][j]; band[c][j] = 0; }
                bs_clear(&b[c]);
            }
            r[2 * E_N] = agree;
            agree = 0;
        }
    }
    int64_t nw = nb - 1 < n_win ? nb - 1 : n_win;
    for (int64_t t = 0; t < nw; t++) {
        int64_t *r0 = blk + t * (2 * E_N + 1), *r1 = r0 + (2 * E_N + 1);
        int64_t v[2][10];
        for (int c = 0; c < 2; c++) {
            int64_t *a = r0 + c * E_N, *bb = r1 + c * E_N;
            v[c][0] = ilog2_fx(a[E_MAV] + bb[E_MAV]);
            v[c][1] = ilog2_fx(a[E_LL] + bb[E_LL]);
            v[c][2] = v[c][1] - v[c][0];
            v[c][3] = a[E_ZC] + bb[E_ZC];
            v[c][4] = a[E_EXT] + bb[E_EXT];
            for (int j = 0; j < 5; j++) v[c][5 + j] = ilog2_fx(a[E_DELTA + j] + bb[E_DELTA + j]);
            int64_t wb = a[E_BROAD] + bb[E_BROAD];
            art[t * 2 + c] = (wb < ART_LOW_SUM) || (wb > ART_HIGH_SUM);
            for (int j = 0; j < 10; j++) X_(t, CH_FEAT[c][j]) = v[c][j];
        }
        for (int j = 0; j < 10; j++) {
            int64_t a = v[0][j], bb = v[1][j];
            X_(t, CROSS_FEAT[j][0]) = asr(a + bb, 1);
            X_(t, CROSS_FEAT[j][1]) = a > bb ? a : bb;
            X_(t, CROSS_FEAT[j][2]) = iabs(a - bb);
        }
        X_(t, F_eeg_sign_agree) = r0[2 * E_N] + r1[2 * E_N];
        X_(t, F_eeg_art_ch1) = art[t * 2];
        X_(t, F_eeg_art_ch2) = art[t * 2 + 1];
    }
    free(blk);
    return 0;
}

/* ------------------------------------------------------------------------------------------- ECG */
static int64_t upper_bound(const int64_t *a, int64_t n, int64_t v) {   /* number of a[i] <= v (a sorted) */
    int64_t lo = 0, hi = n;
    while (lo < hi) { int64_t m = (lo + hi) / 2; if (a[m] <= v) lo = m + 1; else hi = m; }
    return lo;
}

static int ecg(int64_t n_win, const int16_t *x, int64_t n, int64_t *X) {
    int64_t cap = n / ECG_REFRACTORY + 2, nbeat = 0;
    int64_t *beats = malloc((size_t)cap * sizeof(int64_t));
    if (!beats) return -1;
    bq_t f1 = {0}, f2 = {0};
    int64_t r_hist[ECG_INTEG] = {0}, m = 0, spk = 0, npk = 0, last_beat = -ECG_REFRACTORY, cand = 0, cand_i = -1;
    int64_t prev_m = 0, e1 = 0, e2 = 0;
    int rising = 0;
    for (int64_t i = 0; i < n; i++) {
        int64_t e = bq(&f2, &C_ecg_lp15, bq(&f1, &C_ecg_hp5, x[i]));
        int64_t d = e - (i >= 2 ? e2 : 0);
        e2 = e1; e1 = e;
        int64_t r = iabs(d);
        m += r - r_hist[i % ECG_INTEG];
        r_hist[i % ECG_INTEG] = r;
        if (i < ECG_WARMUP) {
            if (m > spk) { spk = m; npk = asr(spk, 3); }
            prev_m = m;
            continue;
        }
        if (m > prev_m) {
            rising = 1;
            if (m > cand) { cand = m; cand_i = i; }
        } else if (rising && m < prev_m) {
            rising = 0;
            int64_t thr = npk + asr(spk - npk, ECG_THR_SHIFT);
            if (cand > thr && cand_i - last_beat >= ECG_REFRACTORY) {
                if (nbeat < cap) beats[nbeat++] = cand_i;
                last_beat = cand_i;
                spk += asr(cand - spk, ECG_SPK_SHIFT);
            } else {
                npk += asr(cand - npk, ECG_SPK_SHIFT);
            }
            cand = 0;
        }
        prev_m = m;
    }
    /* RR intervals (time stamp = closing beat), their absolute successive differences, out-of-range flags */
    int64_t nrr = nbeat > 1 ? nbeat - 1 : 0, nd = nrr > 1 ? nrr - 1 : 0;
    int64_t *rr = malloc((size_t)(nrr + 1) * sizeof(int64_t)), *rr_t = malloc((size_t)(nrr + 1) * sizeof(int64_t));
    int64_t *c_rr = calloc((size_t)(nrr + 1), sizeof(int64_t)), *c_bad = calloc((size_t)(nrr + 1), sizeof(int64_t));
    int64_t *c_d = calloc((size_t)(nd + 1), sizeof(int64_t)), *d_t = malloc((size_t)(nd + 1) * sizeof(int64_t));
    if (!rr || !rr_t || !c_rr || !c_bad || !c_d || !d_t) return -1;
    for (int64_t k = 0; k < nrr; k++) {
        rr[k] = beats[k + 1] - beats[k];
        rr_t[k] = beats[k + 1];
        c_rr[k + 1] = c_rr[k] + rr[k];
        c_bad[k + 1] = c_bad[k] + (rr[k] < ECG_RR_MIN || rr[k] > ECG_RR_MAX);
    }
    for (int64_t k = 0; k < nd; k++) {
        c_d[k + 1] = c_d[k] + iabs(rr[k + 1] - rr[k]);
        d_t[k] = rr_t[k + 1];
    }
    for (int64_t t = 0; t < n_win; t++) {
        int64_t end = (t + 2) * FS_BIO, lo = end - ECG_HR_WINDOW_S * FS_BIO;
        int64_t i1 = upper_bound(rr_t, nrr, end), i0 = upper_bound(rr_t, nrr, lo);
        int64_t s_rr = c_rr[i1] - c_rr[i0], n_rr = i1 - i0, n_bad = c_bad[i1] - c_bad[i0];
        int64_t j1 = upper_bound(d_t, nd, end), j0 = upper_bound(d_t, nd, lo);
        int64_t s_d = c_d[j1] - c_d[j0], n_d = j1 - j0;
        int64_t last = upper_bound(beats, nbeat, end) - 1;
        int64_t since = (nbeat > 0 && last >= 0) ? end - beats[last] : end;
        X_(t, F_ecg_quality_bad) = (n_rr < ECG_MIN_RR) || (n_bad > 0) || (since > ECG_MAX_GAP_S * FS_BIO);
        X_(t, F_ecg_log_rr) = n_rr > 0 ? ilog2_fx(s_rr) - ilog2_fx(n_rr) : 0;
        X_(t, F_ecg_log_masrd) = n_d > 0 ? ilog2_fx(s_d > 1 ? s_d : 1) - ilog2_fx(n_d > 1 ? n_d : 1) : 0;
    }
    free(beats); free(rr); free(rr_t); free(c_rr); free(c_bad); free(c_d); free(d_t);
    return 0;
}

/* ------------------------------------------------------------------------------------------- EMG */
static int emg(int64_t n_win, const int16_t *x, int64_t n, int64_t *X) {
    int64_t nb = n / BLOCK_BIO;
    int64_t *blk = calloc((size_t)(nb > 0 ? nb : 1) * 5, sizeof(int64_t));
    if (!blk) return -1;
    bq_t hp = {0}, lp = {0}, hh = {0};
    bs_t b = {0};
    int64_t low = 0, high = 0;
    for (int64_t i = 0; i < nb * BLOCK_BIO; i++) {
        int64_t g = bq(&hp, &C_emg_hp20, x[i]);
        bs_step(&b, g);
        low += iabs(bq(&lp, &C_emg_lp60, g));
        high += iabs(bq(&hh, &C_emg_hp60, g));
        if ((i + 1) % BLOCK_BIO == 0) {
            int64_t *r = blk + (i / BLOCK_BIO) * 5;
            r[0] = b.mav; r[1] = b.ll; r[2] = b.zc; r[3] = low; r[4] = high;
            bs_clear(&b); low = high = 0;
        }
    }
    int64_t nw = nb - 1 < n_win ? nb - 1 : n_win;
    for (int64_t t = 0; t < nw; t++) {
        int64_t *a = blk + t * 5, *c = a + 5;
        X_(t, F_emg_mav) = ilog2_fx(a[0] + c[0]);
        X_(t, F_emg_ll) = ilog2_fx(a[1] + c[1]);
        X_(t, F_emg_zc) = a[2] + c[2];
        X_(t, F_emg_hl_ratio) = ilog2_fx(a[4] + c[4]) - ilog2_fx(a[3] + c[3]);
    }
    free(blk);
    return 0;
}

/* ------------------------------------------------------------------------------------------- motion */
static int motion(int64_t n_win, const int16_t *ax[3], int64_t n, int f_mag, int f_jerk, int f_act, int f_band,
                  int64_t *X) {
    int64_t nb = n / BLOCK_MOV;
    int64_t *blk = calloc((size_t)(nb > 0 ? nb : 1) * 4, sizeof(int64_t));
    if (!blk) return -1;
    int64_t m[3];
    bs_t b[3];
    bq_t f1[3], f2[3];
    memset(b, 0, sizeof b); memset(f1, 0, sizeof f1); memset(f2, 0, sizeof f2);
    for (int a = 0; a < 3; a++) m[a] = n > 0 ? shl(ax[a][0], EMA_GUARD_BITS) : 0;
    int64_t mag = 0, act = 0, band = 0;
    for (int64_t i = 0; i < nb * BLOCK_MOV; i++) {
        int64_t l1 = 0;
        for (int a = 0; a < 3; a++) {
            int64_t xi = shl(ax[a][i], EMA_GUARD_BITS);
            int64_t y = asr(xi - m[a], EMA_GUARD_BITS);
            m[a] += asr(xi - m[a], MOV_OFFSET_SHIFT);
            l1 += iabs(y);
            bs_step(&b[a], y);
            band += iabs(bq(&f2[a], &C_mov_lp5, bq(&f1[a], &C_mov_hp1, ax[a][i])));
        }
        mag += l1;
        act += l1 > MOV_ACT_THR;
        if ((i + 1) % BLOCK_MOV == 0) {
            int64_t *r = blk + (i / BLOCK_MOV) * 4;
            r[0] = mag; r[1] = b[0].ll + b[1].ll + b[2].ll; r[2] = act; r[3] = band;
            for (int a = 0; a < 3; a++) bs_clear(&b[a]);
            mag = act = band = 0;
        }
    }
    int64_t nw = nb - 1 < n_win ? nb - 1 : n_win;
    for (int64_t t = 0; t < nw; t++) {
        int64_t *a = blk + t * 4, *c = a + 4;
        X_(t, f_mag) = ilog2_fx(a[0] + c[0]);
        X_(t, f_jerk) = ilog2_fx(a[1] + c[1]);
        X_(t, f_act) = a[2] + c[2];
        X_(t, f_band) = ilog2_fx(a[3] + c[3]);
    }
    free(blk);
    return 0;
}

/* ------------------------------------------------------------------------------------------- run level */
static int64_t n_present(int64_t n_win, int64_t n, int fs) {
    int64_t k = n / fs - 1;
    if (k < 0) k = 0;
    return k < n_win ? k : n_win;
}

/* X: n_win x N_FEATURES int64 (zeroed by the caller or here), art: n_win x 2. NULL pointers = absent sensor.
 * Returns 0 on success. */
int fe_extract(int64_t n_win, const int16_t *eeg1, const int16_t *eeg2, int64_t n_eeg,
               const int16_t *ecg_x, int64_t n_ecg, const int16_t *emg_x, int64_t n_emg,
               const int16_t *acc_x, const int16_t *acc_y, const int16_t *acc_z, int64_t n_acc,
               const int16_t *gyr_x, const int16_t *gyr_y, const int16_t *gyr_z, int64_t n_gyr,
               int64_t *X, uint8_t *art) {
    memset(X, 0, (size_t)n_win * N_FEATURES * sizeof(int64_t));
    memset(art, 0, (size_t)n_win * 2);
    if (eeg(n_win, eeg1, eeg2, n_eeg, X, art)) return -1;
    int64_t pres[4] = {0, 0, 0, 0};
    if (ecg_x && n_ecg > 0) { if (ecg(n_win, ecg_x, n_ecg, X)) return -2; pres[0] = n_present(n_win, n_ecg, FS_BIO); }
    if (emg_x && n_emg > 0) { if (emg(n_win, emg_x, n_emg, X)) return -3; pres[1] = n_present(n_win, n_emg, FS_BIO); }
    if (acc_x && acc_y && acc_z && n_acc > 0) {
        const int16_t *a[3] = {acc_x, acc_y, acc_z};
        if (motion(n_win, a, n_acc, F_mov_acc_mag, F_mov_acc_jerk, F_mov_acc_act, F_mov_acc_band, X)) return -4;
        pres[2] = n_present(n_win, n_acc, FS_MOV);
    }
    if (gyr_x && gyr_y && gyr_z && n_gyr > 0) {
        const int16_t *g[3] = {gyr_x, gyr_y, gyr_z};
        if (motion(n_win, g, n_gyr, F_mov_gyr_mag, F_mov_gyr_jerk, F_mov_gyr_act, F_mov_gyr_band, X)) return -5;
        pres[3] = n_present(n_win, n_gyr, FS_MOV);
    }
    /* missing-modality rule: an absent sensor's features are zero */
    static const char *prefix[4] = {"ecg_", "emg_", "mov_acc_", "mov_gyr_"};
    static const int pres_col[4] = {F_present_ecg, F_present_emg, F_present_mov_acc, F_present_mov_gyr};
    for (int j = 0; j < 4; j++) {
        for (int f = 0; f < N_FEATURES; f++) {
            if (strncmp(FEATURE_NAMES[f], prefix[j], strlen(prefix[j])) != 0) continue;
            for (int64_t t = pres[j]; t < n_win; t++) X_(t, f) = 0;
        }
        for (int64_t t = 0; t < n_win; t++) X_(t, pres_col[j]) = t < pres[j];
    }
    /* context: difference from a causal 64-s EMA, started at the first valid window, held while invalid */
    for (int j = 0; j < N_CTX; j++) {
        int mod = CTX_MOD[j], started = 0;
        int64_t e = 0;
        for (int64_t t = 0; t < n_win; t++) {
            int valid = mod < 0 ? 1 : t < pres[mod];
            if (!valid) { X_(t, CTX_DST[j]) = 0; continue; }
            int64_t f = X_(t, CTX_SRC[j]), v = shl(f, EMA_GUARD_BITS);
            if (!started) { e = v; started = 1; }
            X_(t, CTX_DST[j]) = f - asr(e, EMA_GUARD_BITS);
            e += asr(v - e, CONTEXT_SHIFT);
        }
    }
    return 0;
}

int fe_n_features(void) { return N_FEATURES; }

#ifdef FE_MAIN
/* seizelut_fe <n_win> <out_features.i16> <out_artefact.u8> <eeg1> <eeg2> [ecg|-] [emg|-] [ax ay az|- - -] [gx gy gz|- - -] */
static int16_t *load(const char *p, int64_t *n) {
    *n = 0;
    if (!p || !strcmp(p, "-")) return NULL;
    FILE *f = fopen(p, "rb");
    if (!f) { fprintf(stderr, "cannot open %s\n", p); exit(2); }
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    int16_t *b = malloc((size_t)sz);
    if (fread(b, 1, (size_t)sz, f) != (size_t)sz) { fprintf(stderr, "short read %s\n", p); exit(2); }
    fclose(f);
    *n = sz / 2;
    return b;
}

int main(int argc, char **argv) {
    if (argc < 6) { fprintf(stderr, "usage: %s n_win out.i16 out_art.u8 eeg1 eeg2 [ecg emg ax ay az gx gy gz]\n", argv[0]); return 2; }
    int64_t n_win = atoll(argv[1]), ne, n1, n2, nc = 0, nm = 0, na = 0, nb = 0, nc2 = 0, ng = 0, t;
    const char *a[13] = {0};
    for (int i = 4; i < argc && i < 17; i++) a[i - 4] = argv[i];
    int16_t *e1 = load(a[0], &n1), *e2 = load(a[1], &n2), *c = load(a[2], &nc), *m = load(a[3], &nm);
    int16_t *ax = load(a[4], &na), *ay = load(a[5], &t), *az = load(a[6], &t);
    int16_t *gx = load(a[7], &ng), *gy = load(a[8], &nb), *gz = load(a[9], &nc2);
    ne = n1 < n2 ? n1 : n2;
    int64_t *X = malloc((size_t)n_win * N_FEATURES * sizeof(int64_t));
    uint8_t *art = malloc((size_t)n_win * 2);
    int rc = fe_extract(n_win, e1, e2, ne, c, nc, m, nm, ax, ay, az, na, gx, gy, gz, ng, X, art);
    if (rc) { fprintf(stderr, "fe_extract failed %d\n", rc); return 1; }
    FILE *fo = fopen(argv[2], "wb");
    for (int64_t i = 0; i < n_win * N_FEATURES; i++) { int16_t v = (int16_t)X[i]; fwrite(&v, 2, 1, fo); }
    fclose(fo);
    fo = fopen(argv[3], "wb");
    fwrite(art, 1, (size_t)n_win * 2, fo);
    fclose(fo);
    return 0;
}
#endif
