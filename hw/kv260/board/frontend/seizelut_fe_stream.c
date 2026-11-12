/* SeizeLUT integer front end, streaming version for the live demo: one second of samples in, one window of features
 * out, exactly as the batch fe_extract() computes them for the same samples (verified window by window).
 *
 * Push block b (second b: 256 samples per biopotential channel, 25 per motion axis). Window w covers seconds
 * [w, w+2); it is emitted after block w+2, one second late, because an R-peak is confirmed a few samples after it
 * happens and the ECG features of window w count every beat up to the end of second w+1. The first window comes
 * out after block 2. A sensor that is absent (NULL) must stay absent for the whole stream, as in the batch code.
 *
 * For the dashboard, every push also returns the second's band-passed EEG (both channels), filtered ECG and EMG,
 * the R-peaks detected during that second, and the motion magnitude.
 * Build: gcc -O2 -shared -fPIC -o libseizelut_fe.so seizelut_fe_stream.c   (includes the batch code as well)
 */
#include "seizelut_fe.c"

#define RING 4                     /* block summaries kept: b-2, b-1, b (and one spare) */
#define MAXB 256                   /* beats kept for the RR statistics (about a minute) */

typedef struct {
    /* EEG: filters, block statistics, band sums, one ring of per-block summaries */
    bq_t ef[2][14];
    bs_t eb[2];
    int64_t eblk[RING][2 * E_N + 1];
    /* EMG */
    bq_t gf[3];
    bs_t gb;
    int64_t gblk[RING][5];
    /* motion: per sensor (acc, gyr) */
    int64_t mm[2][3];
    int m_init[2];
    bs_t mb[2][3];
    bq_t mf1[2][3], mf2[2][3];
    int64_t mblk[RING][2][4];
    /* ECG: filters and R-peak detector state */
    bq_t cf1, cf2;
    int64_t r_hist[ECG_INTEG], m, spk, npk, last_beat, cand, cand_i, prev_m, e1, e2, n_ecg;
    int rising;
    int64_t bt[MAXB], brr[MAXB], bdrr[MAXB];   /* every beat: time, RR closing at it, |RR - previous RR| */
    uint8_t bhas_rr[MAXB], bhas_d[MAXB], bbad[MAXB];
    int nb_beats;                  /* beats in the buffer (oldest first) */
    int64_t dropped_last;          /* time of the newest beat dropped from the buffer, -1 if none */
    int64_t prev_beat_t, prev_rr;  /* for the RR of the next beat */
    int have_beat, have_prev_rr;
    /* context EMAs and presence */
    int64_t ctx_e[N_CTX];
    int ctx_started[N_CTX];
    int present[4];                /* ECG, EMG, ACC, GYR, fixed by the first push */
    int64_t blocks;                /* blocks pushed */
} fe_stream;

fe_stream *fes_new(void) { return calloc(1, sizeof(fe_stream)); }
void fes_free(fe_stream *s) { free(s); }
void fes_reset(fe_stream *s) { memset(s, 0, sizeof(*s)); }

static void drop_beats(fe_stream *s, int k) {
    if (k <= 0) return;
    s->dropped_last = s->bt[k - 1];
    int m = s->nb_beats - k;
    memmove(s->bt, s->bt + k, m * sizeof(int64_t));
    memmove(s->brr, s->brr + k, m * sizeof(int64_t));
    memmove(s->bdrr, s->bdrr + k, m * sizeof(int64_t));
    memmove(s->bhas_rr, s->bhas_rr + k, m);
    memmove(s->bhas_d, s->bhas_d + k, m);
    memmove(s->bbad, s->bbad + k, m);
    s->nb_beats = m;
}

static void ecg_beat(fe_stream *s, int64_t t) {
    if (s->nb_beats == MAXB) drop_beats(s, 1);
    int k = s->nb_beats++;
    s->bt[k] = t;
    s->bhas_rr[k] = s->have_beat;
    s->brr[k] = s->have_beat ? t - s->prev_beat_t : 0;
    s->bbad[k] = s->have_beat && ((s->brr[k] < ECG_RR_MIN) || (s->brr[k] > ECG_RR_MAX));
    s->bhas_d[k] = s->have_beat && s->have_prev_rr;
    s->bdrr[k] = s->bhas_d[k] ? iabs(s->brr[k] - s->prev_rr) : 0;
    if (s->have_beat) { s->prev_rr = s->brr[k]; s->have_prev_rr = 1; }
    s->prev_beat_t = t;
    s->have_beat = 1;
}

/* one ECG sample through the filters and the R-peak detector (same code as ecg() in seizelut_fe.c) */
static int64_t ecg_sample(fe_stream *s, int64_t x, int64_t *beat_at) {
    int64_t i = s->n_ecg++;
    int64_t e = bq(&s->cf2, &C_ecg_lp15, bq(&s->cf1, &C_ecg_hp5, x));
    int64_t d = e - (i >= 2 ? s->e2 : 0);
    s->e2 = s->e1; s->e1 = e;
    int64_t r = iabs(d);
    s->m += r - s->r_hist[i % ECG_INTEG];
    s->r_hist[i % ECG_INTEG] = r;
    *beat_at = -1;
    if (i < ECG_WARMUP) {
        if (s->m > s->spk) { s->spk = s->m; s->npk = asr(s->spk, 3); }
        s->prev_m = s->m;
        return e;
    }
    if (s->m > s->prev_m) {
        s->rising = 1;
        if (s->m > s->cand) { s->cand = s->m; s->cand_i = i; }
    } else if (s->rising && s->m < s->prev_m) {
        s->rising = 0;
        int64_t thr = s->npk + asr(s->spk - s->npk, ECG_THR_SHIFT);
        if (s->cand > thr && s->cand_i - s->last_beat >= ECG_REFRACTORY) {
            ecg_beat(s, s->cand_i);
            *beat_at = s->cand_i;
            s->last_beat = s->cand_i;
            s->spk += asr(s->cand - s->spk, ECG_SPK_SHIFT);
        } else {
            s->npk += asr(s->cand - s->npk, ECG_SPK_SHIFT);
        }
        s->cand = 0;
    }
    s->prev_m = s->m;
    return e;
}

/* window w (seconds [w, w+2)) from the block summaries of seconds w and w+1 and the beats confirmed so far */
static void fes_emit(fe_stream *s, int64_t w, int64_t *X, uint8_t *art) {
    int r0 = (int)(w % RING), r1 = (int)((w + 1) % RING);
    memset(X, 0, N_FEATURES * sizeof(int64_t));
    {
        int64_t v[2][10];
        for (int c = 0; c < 2; c++) {
            int64_t *a = s->eblk[r0] + c * E_N, *bb = s->eblk[r1] + c * E_N;
            v[c][0] = ilog2_fx(a[E_MAV] + bb[E_MAV]);
            v[c][1] = ilog2_fx(a[E_LL] + bb[E_LL]);
            v[c][2] = v[c][1] - v[c][0];
            v[c][3] = a[E_ZC] + bb[E_ZC];
            v[c][4] = a[E_EXT] + bb[E_EXT];
            for (int j = 0; j < 5; j++) v[c][5 + j] = ilog2_fx(a[E_DELTA + j] + bb[E_DELTA + j]);
            int64_t wb = a[E_BROAD] + bb[E_BROAD];
            art[c] = (wb < ART_LOW_SUM) || (wb > ART_HIGH_SUM);
            for (int j = 0; j < 10; j++) X[CH_FEAT[c][j]] = v[c][j];
        }
        for (int j = 0; j < 10; j++) {
            int64_t a = v[0][j], bb = v[1][j];
            X[CROSS_FEAT[j][0]] = asr(a + bb, 1);
            X[CROSS_FEAT[j][1]] = a > bb ? a : bb;
            X[CROSS_FEAT[j][2]] = iabs(a - bb);
        }
        X[F_eeg_sign_agree] = s->eblk[r0][2 * E_N] + s->eblk[r1][2 * E_N];
        X[F_eeg_art_ch1] = art[0];
        X[F_eeg_art_ch2] = art[1];
    }
    if (s->present[0]) {
        int64_t end = (w + 2) * FS_BIO, lo = end - ECG_HR_WINDOW_S * FS_BIO;
        int64_t s_rr = 0, n_rr = 0, n_bad = 0, s_d = 0, n_d = 0, last = s->dropped_last;
        for (int k = 0; k < s->nb_beats; k++) {
            int64_t t = s->bt[k];
            if (t <= end) last = t;
            if (t > lo && t <= end) {
                if (s->bhas_rr[k]) { s_rr += s->brr[k]; n_rr++; n_bad += s->bbad[k]; }
                if (s->bhas_d[k]) { s_d += s->bdrr[k]; n_d++; }
            }
        }
        int64_t since = last >= 0 ? end - last : end;
        X[F_ecg_quality_bad] = (n_rr < ECG_MIN_RR) || (n_bad > 0) || (since > ECG_MAX_GAP_S * FS_BIO);
        X[F_ecg_log_rr] = n_rr > 0 ? ilog2_fx(s_rr) - ilog2_fx(n_rr) : 0;
        X[F_ecg_log_masrd] = n_d > 0 ? ilog2_fx(s_d > 1 ? s_d : 1) - ilog2_fx(n_d > 1 ? n_d : 1) : 0;
        /* forget beats that can no longer fall into a window (windows only move forward) */
        int drop = 0;
        while (drop < s->nb_beats && s->bt[drop] <= lo) drop++;
        drop_beats(s, drop);
    }
    if (s->present[1]) {
        int64_t *a = s->gblk[r0], *c = s->gblk[r1];
        X[F_emg_mav] = ilog2_fx(a[0] + c[0]);
        X[F_emg_ll] = ilog2_fx(a[1] + c[1]);
        X[F_emg_zc] = a[2] + c[2];
        X[F_emg_hl_ratio] = ilog2_fx(a[4] + c[4]) - ilog2_fx(a[3] + c[3]);
    }
    static const int MF[2][4] = {{F_mov_acc_mag, F_mov_acc_jerk, F_mov_acc_act, F_mov_acc_band},
                                 {F_mov_gyr_mag, F_mov_gyr_jerk, F_mov_gyr_act, F_mov_gyr_band}};
    for (int sn = 0; sn < 2; sn++) {
        if (!s->present[2 + sn]) continue;
        int64_t *a = s->mblk[r0][sn], *c = s->mblk[r1][sn];
        X[MF[sn][0]] = ilog2_fx(a[0] + c[0]);
        X[MF[sn][1]] = ilog2_fx(a[1] + c[1]);
        X[MF[sn][2]] = a[2] + c[2];
        X[MF[sn][3]] = ilog2_fx(a[3] + c[3]);
    }
    X[F_present_ecg] = s->present[0]; X[F_present_emg] = s->present[1];
    X[F_present_mov_acc] = s->present[2]; X[F_present_mov_gyr] = s->present[3];
    for (int j = 0; j < N_CTX; j++) {
        int mod = CTX_MOD[j];
        if (mod >= 0 && !s->present[mod]) { X[CTX_DST[j]] = 0; continue; }
        int64_t f = X[CTX_SRC[j]], v = shl(f, EMA_GUARD_BITS);
        if (!s->ctx_started[j]) { s->ctx_e[j] = v; s->ctx_started[j] = 1; }
        X[CTX_DST[j]] = f - asr(s->ctx_e[j], EMA_GUARD_BITS);
        s->ctx_e[j] += asr(v - s->ctx_e[j], CONTEXT_SHIFT);
    }
}


/* Returns 1 when window *w_out was emitted into X (117 features, spec order) and art (2 flags), else 0.
 * Visualisation outputs (any may be NULL): xbp1/xbp2/ecgf/emgf 256 values, accm/gyrm 25 values, beats: offsets in
 * samples from the start of this second of the R-peaks confirmed during it (can be slightly negative), n_beats. */
int fes_push(fe_stream *s, const int16_t *eeg1, const int16_t *eeg2, const int16_t *ecg_x, const int16_t *emg_x,
             const int16_t *ax, const int16_t *ay, const int16_t *az, const int16_t *gx, const int16_t *gy,
             const int16_t *gz, int64_t *X, uint8_t *art, int64_t *w_out,
             int32_t *xbp1, int32_t *xbp2, int32_t *ecgf, int32_t *emgf, int32_t *accm, int32_t *gyrm,
             int32_t *beats, int32_t *n_beats) {
    int64_t b = s->blocks;
    if (b == 0) {
        memset(s, 0, sizeof(*s));
        s->last_beat = -ECG_REFRACTORY;
        s->cand_i = -1;
        s->dropped_last = -1;
        s->present[0] = ecg_x != NULL; s->present[1] = emg_x != NULL;
        s->present[2] = ax && ay && az; s->present[3] = gx && gy && gz;
    }
    int r = (int)(b % RING);
    /* ---- EEG */
    {
        const int16_t *xs[2] = {eeg1, eeg2};
        int64_t band[2][6] = {{0}}, agree = 0;
        for (int i = 0; i < BLOCK_BIO; i++) {
            int sg[2];
            for (int c = 0; c < 2; c++) {
                int64_t q = xs[c][i];
                bq_t *f = s->ef[c];
                int64_t h1 = bq(&f[0], &C_eeg_hp1, q);
                int64_t xbp = bq(&f[1], &C_eeg_lp25, h1);
                int64_t de = bq(&f[2], &C_eeg_lp4, h1);
                int64_t th = bq(&f[4], &C_eeg_lp8, bq(&f[3], &C_eeg_hp4, q));
                int64_t al = bq(&f[6], &C_eeg_lp13, bq(&f[5], &C_eeg_hp8, q));
                int64_t be = bq(&f[8], &C_eeg_lp25, bq(&f[7], &C_eeg_hp13, q));
                int64_t hf = bq(&f[10], &C_eeg_lp60, bq(&f[9], &C_eeg_hp25, q));
                int64_t br = bq(&f[13], &C_eeg_notch50, bq(&f[12], &C_eeg_lp60, bq(&f[11], &C_eeg_hp05, q)));
                bs_step(&s->eb[c], xbp);
                band[c][0] += iabs(de); band[c][1] += iabs(th); band[c][2] += iabs(al);
                band[c][3] += iabs(be); band[c][4] += iabs(hf); band[c][5] += iabs(br);
                sg[c] = xbp >= 0;
                if (c == 0 && xbp1) xbp1[i] = (int32_t)xbp;
                if (c == 1 && xbp2) xbp2[i] = (int32_t)xbp;
            }
            agree += (sg[0] == sg[1]);
        }
        for (int c = 0; c < 2; c++) {
            int64_t *rc = s->eblk[r] + c * E_N;
            rc[E_MAV] = s->eb[c].mav; rc[E_LL] = s->eb[c].ll; rc[E_ZC] = s->eb[c].zc; rc[E_EXT] = s->eb[c].ext;
            for (int j = 0; j < 6; j++) rc[E_DELTA + j] = band[c][j];
            bs_clear(&s->eb[c]);
        }
        s->eblk[r][2 * E_N] = agree;
    }
    /* ---- ECG */
    if (n_beats) *n_beats = 0;
    if (s->present[0]) {
        for (int i = 0; i < BLOCK_BIO; i++) {
            int64_t at;
            int64_t e = ecg_sample(s, ecg_x[i], &at);
            if (ecgf) ecgf[i] = (int32_t)e;
            if (at >= 0 && beats && n_beats && *n_beats < 16) beats[(*n_beats)++] = (int32_t)(at - b * BLOCK_BIO);
        }
    }
    /* ---- EMG */
    if (s->present[1]) {
        int64_t low = 0, high = 0;
        for (int i = 0; i < BLOCK_BIO; i++) {
            int64_t g = bq(&s->gf[0], &C_emg_hp20, emg_x[i]);
            bs_step(&s->gb, g);
            low += iabs(bq(&s->gf[1], &C_emg_lp60, g));
            high += iabs(bq(&s->gf[2], &C_emg_hp60, g));
            if (emgf) emgf[i] = (int32_t)g;
        }
        int64_t *rc = s->gblk[r];
        rc[0] = s->gb.mav; rc[1] = s->gb.ll; rc[2] = s->gb.zc; rc[3] = low; rc[4] = high;
        bs_clear(&s->gb);
    }
    /* ---- motion */
    for (int sn = 0; sn < 2; sn++) {
        if (!s->present[2 + sn]) continue;
        const int16_t *a[3] = {sn ? gx : ax, sn ? gy : ay, sn ? gz : az};
        if (!s->m_init[sn]) { for (int k = 0; k < 3; k++) s->mm[sn][k] = shl(a[k][0], EMA_GUARD_BITS); s->m_init[sn] = 1; }
        int64_t mag = 0, act = 0, band = 0;
        for (int i = 0; i < BLOCK_MOV; i++) {
            int64_t l1 = 0;
            for (int k = 0; k < 3; k++) {
                int64_t xi = shl(a[k][i], EMA_GUARD_BITS);
                int64_t y = asr(xi - s->mm[sn][k], EMA_GUARD_BITS);
                s->mm[sn][k] += asr(xi - s->mm[sn][k], MOV_OFFSET_SHIFT);
                l1 += iabs(y);
                bs_step(&s->mb[sn][k], y);
                band += iabs(bq(&s->mf2[sn][k], &C_mov_lp5, bq(&s->mf1[sn][k], &C_mov_hp1, a[k][i])));
            }
            mag += l1;
            act += l1 > MOV_ACT_THR;
            int32_t *dst = sn ? gyrm : accm;
            if (dst) dst[i] = (int32_t)l1;
        }
        int64_t *rc = s->mblk[r][sn];
        rc[0] = mag; rc[1] = s->mb[sn][0].ll + s->mb[sn][1].ll + s->mb[sn][2].ll; rc[2] = act; rc[3] = band;
        for (int k = 0; k < 3; k++) bs_clear(&s->mb[sn][k]);
    }
    s->blocks = b + 1;
    if (b < 2) return 0;
    fes_emit(s, b - 2, X, art);
    *w_out = b - 2;
    return 1;
}

/* After the last block: the final window, which has no look-ahead block (as in the batch code at the end of a
 * recording). Returns 1 if a window was emitted. */
int fes_flush(fe_stream *s, int64_t *X, uint8_t *art, int64_t *w_out) {
    if (s->blocks < 2) return 0;
    fes_emit(s, s->blocks - 2, X, art);
    *w_out = s->blocks - 2;
    return 1;
}

int fes_n_features(void) { return N_FEATURES; }
