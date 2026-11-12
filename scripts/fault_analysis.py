#!/usr/bin/env python3
"""N9: every single hardware fault of the deployed classifier, what it does to the decisions, and which self-test
vectors catch it. Training patients only (the 96 patients the final model was trained on); no test patient is read.

Fault list (the classifier as built in the fabric: 146 comparators -> 50 LUT6 -> popcount score -> decision -> alarm):
  tt   one flipped truth-table bit: LUT j, address a (50 x 64 = 3,200 faults; a configuration-memory upset)
  sab  comparator output i stuck at 0 or 1 (146 x 2 = 292 faults)
  sal  LUT output j stuck at 0 or 1 (50 x 2 = 100 faults)
For every fault and every window of the 96 training patients (2,072 recordings) we compute the faulty score and
count the windows whose decision changes at three operating points (frozen threshold 9, programmable 2 and -7, as in
the hardware) and the windows whose alarm (10 of the last 10 decisions, from the start of each recording) changes.

A self-test vector set detects a fault when the faulty score differs from the golden score on at least one vector
(the on-chip BIST compares score, decision and alarm of every vector). Coverage is reported for the 1,024 vectors in
the current BIST ROM (a seizure stretch of an exported recording) and for a set chosen to cover every fault that is
observable on the training data: rarest truth-table entries first, then the stuck-at faults still undetected.

Outputs: results/tables/fault_analysis.json, cache/fault/selected_vectors.npz (features, artefact flags and golden
outputs of the selected vectors, for the BIST ROM).
Usage: python scripts/fault_analysis.py [--workers 4] [--max-runs N]
"""
from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
EXPORT = REPO / "export" / "n4_distill_s0"
OUT = REPO / "results" / "tables" / "fault_analysis.json"
SEL = REPO / "cache" / "fault" / "selected_vectors.npz"
THRS = (9, 2, -7)
K, N = 10, 10


def load_model():
    th = json.loads((EXPORT / "thresholds.json").read_text())
    mp = json.loads((EXPORT / "mapping.json").read_text())
    lt = json.loads((EXPORT / "luts.json").read_text())
    hd = json.loads((EXPORT / "head.json").read_text())
    assert len(mp["layers"]) == 1
    col = {f["name"]: i for i, f in enumerate(th["features"])}
    spec = np.array([f["spec_index"] for f in th["features"]])
    bit_col = np.array([col[b["feature"]] for b in th["input_bits"]])
    bit_thr = np.array([b["threshold"] for b in th["input_bits"]], dtype=np.int64)
    maps = np.array(mp["layers"][0]["inputs"], dtype=np.int64)               # (50, 6)
    tt = np.array([[(int(t, 16) >> a) & 1 for a in range(64)] for t in lt["layers"][0]], dtype=np.int8)
    sign = np.zeros(len(tt), dtype=np.int64)
    sign[slice(*hd["groups"]["seizure"])] = 1
    sign[slice(*hd["groups"]["background"])] = -1
    assert int(hd["decision_threshold"]) == THRS[0] and int(hd["k"]) == K
    return {"spec": spec, "bit_col": bit_col, "bit_thr": bit_thr, "maps": maps, "tt": tt, "sign": sign}


def forward(M, F):
    """F: (n, 38) features in register order -> bits (n,146) u8, addr (n,50), out (n,50), score (n,)."""
    bits = (F[:, M["bit_col"]] > M["bit_thr"]).astype(np.uint8)
    addr = np.zeros((len(F), len(M["maps"])), dtype=np.int64)
    for lb in range(M["maps"].shape[1]):
        addr |= bits[:, M["maps"][:, lb]].astype(np.int64) << lb
    out = M["tt"][np.arange(len(M["maps"]))[None, :], addr]
    score = (out.astype(np.int64) * M["sign"][None, :]).sum(1)
    return bits, addr, out, score


def alarms(dec):
    d = np.concatenate([np.zeros(N - 1, np.int64), dec.astype(np.int64)])
    c = np.cumsum(np.concatenate([[0], d]))
    return (c[N:] - c[:-N]) >= K


def alarm_changes(dec, alarm, pos):
    """Number of windows whose alarm changes when the decisions at `pos` (sorted) are flipped."""
    if len(pos) == 0:
        return 0
    t = np.unique((pos[:, None] + np.arange(N)[None, :]).ravel())
    t = t[t < len(dec)]
    new = dec.astype(np.int64).copy()
    new[pos] ^= 1
    c = np.cumsum(np.concatenate([np.zeros(N, np.int64), new]))     # c[i + N] = sum(new[:i + 1])
    s = c[t + N] - c[t]                                              # sum of new over [t - N + 1, t]
    return int(((s >= K) != alarm[t]).sum())


def run_one(key):
    """Per-recording fault statistics (all faults), plus the recording's distinct patterns for vector selection."""
    from seizelut.data.featureset import FeatureStore
    M = load_model()
    r = FeatureStore("int").load_run(key)
    F = r.X[:, M["spec"]].astype(np.int64)
    bits, addr, out, score = forward(M, F)
    n, L = addr.shape
    res = {"n": n, "seizure_windows": int((r.y > 0).sum())}
    dec = {t: score >= t for t in THRS}
    alm = {t: alarms(dec[t]) for t in THRS}
    # --- truth-table flips: delta = sign_j * (1 - 2 tt[j, a]) on the windows addressing (j, a)
    tt_hits = np.zeros((L, 64), np.int64)
    tt_dec = {t: np.zeros((L, 64), np.int64) for t in THRS}
    tt_alarm = {t: np.zeros((L, 64), np.int64) for t in THRS}
    for j in range(L):
        a_j = addr[:, j]
        tt_hits[j] = np.bincount(a_j, minlength=64)
        delta = M["sign"][j] * (1 - 2 * M["tt"][j].astype(np.int64))       # per address
        for t in THRS:
            d = delta[a_j]
            flip = np.where(d > 0, score == t - 1, score == t)              # decision crosses the threshold
            idx = np.nonzero(flip)[0]
            if len(idx) == 0:
                continue
            aa = a_j[idx]
            tt_dec[t][j] += np.bincount(aa, minlength=64)
            for a in np.unique(aa):
                tt_alarm[t][j, a] += alarm_changes(dec[t], alm[t], idx[aa == a])
    res["tt_hits"], res["tt_dec"], res["tt_alarm"] = tt_hits, tt_dec, tt_alarm
    # --- stuck-at faults on comparator outputs and on LUT outputs
    users = [np.nonzero((M["maps"] == i).any(1))[0] for i in range(bits.shape[1])]
    sab = {"score": np.zeros((bits.shape[1], 2), np.int64)}
    for t in THRS:
        sab[t] = np.zeros((bits.shape[1], 2), np.int64)
        sab[("a", t)] = np.zeros((bits.shape[1], 2), np.int64)
    for i in range(bits.shape[1]):
        for v in (0, 1):
            ch = bits[:, i] != v
            if not ch.any() or len(users[i]) == 0:
                continue
            ds = np.zeros(n, np.int64)
            for j in users[i]:
                a2 = addr[:, j].copy()
                for lb in np.nonzero(M["maps"][j] == i)[0]:
                    a2 = np.where(ch, (a2 & ~(1 << lb)) | (v << lb), a2)
                ds += M["sign"][j] * (M["tt"][j][a2].astype(np.int64) - out[:, j])
            sab["score"][i, v] = int((ds != 0).sum())
            for t in THRS:
                pos = np.nonzero((score + ds >= t) != dec[t])[0]
                sab[t][i, v] = len(pos)
                sab[("a", t)][i, v] = alarm_changes(dec[t], alm[t], pos)
    sal = {"score": np.zeros((L, 2), np.int64)}
    for t in THRS:
        sal[t] = np.zeros((L, 2), np.int64)
        sal[("a", t)] = np.zeros((L, 2), np.int64)
    for j in range(L):
        for v in (0, 1):
            ds = M["sign"][j] * (v - out[:, j].astype(np.int64))
            sal["score"][j, v] = int((ds != 0).sum())
            for t in THRS:
                pos = np.nonzero((score + ds >= t) != dec[t])[0]
                sal[t][j, v] = len(pos)
                sal[("a", t)][j, v] = alarm_changes(dec[t], alm[t], pos)
    res["sab"], res["sal"] = sab, sal
    # --- candidate self-test vectors: the first window addressing each truth-table entry, plus 64 random windows
    rows = []
    for j in range(L):
        _, first = np.unique(addr[:, j], return_index=True)
        rows.append(first)
    rng = np.random.default_rng(abs(hash(key)) % 2**32)
    rows.append(rng.choice(n, min(n, 64), replace=False))
    rows = np.unique(np.concatenate(rows))
    res["cand"] = (F[rows].astype(np.int16), r.artefact[rows].astype(np.uint8))
    return key, res


def bits_of(packed, nb):
    return np.unpackbits(packed, axis=1)[:, :nb]


def detects(M, bits, faults_sa):
    """For stuck-at faults [(kind, idx, v)], a (n_patterns, n_faults) bool matrix: does the pattern see the fault."""
    _, addr, out, score = forward_bits(M, bits)
    users = [np.nonzero((M["maps"] == i).any(1))[0] for i in range(bits.shape[1])]
    D = np.zeros((len(bits), len(faults_sa)), dtype=bool)
    for f, (kind, i, v) in enumerate(faults_sa):
        if kind == "sal":
            D[:, f] = out[:, i] != v
            continue
        ch = bits[:, i] != v
        ds = np.zeros(len(bits), np.int64)
        for j in users[i]:
            a2 = addr[:, j].copy()
            for lb in np.nonzero(M["maps"][j] == i)[0]:
                a2 = np.where(ch, (a2 & ~(1 << lb)) | (v << lb), a2)
            ds += M["sign"][j] * (M["tt"][j][a2].astype(np.int64) - out[:, j])
        D[:, f] = ds != 0
    return D


def forward_bits(M, bits):
    addr = np.zeros((len(bits), len(M["maps"])), dtype=np.int64)
    for lb in range(M["maps"].shape[1]):
        addr |= bits[:, M["maps"][:, lb]].astype(np.int64) << lb
    out = M["tt"][np.arange(len(M["maps"]))[None, :], addr]
    score = (out.astype(np.int64) * M["sign"][None, :]).sum(1)
    return bits, addr, out, score


def coverage(M, bits, tt_obs, sa_list, sa_obs):
    """Fraction of observable faults detected by the vectors `bits` (tt: addressed entries; sa: score changes)."""
    _, addr, _, _ = forward_bits(M, bits)
    hit = np.zeros(tt_obs.shape, bool)
    for j in range(addr.shape[1]):
        hit[j, np.unique(addr[:, j])] = True
    D = detects(M, bits, sa_list).any(0)
    return hit, D


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-runs", type=int, default=0)
    args = ap.parse_args()
    from seizelut.data.featureset import FeatureStore
    from seizelut.data.split import official_train_subjects
    M = load_model()
    keys = FeatureStore("int").runs_of(official_train_subjects())
    if args.max_runs:
        keys = keys[: args.max_runs]
    L, B = M["tt"].shape[0], len(M["bit_thr"])
    agg = {"n": 0, "seizure_windows": 0, "tt_hits": np.zeros((L, 64), np.int64)}
    for t in THRS:
        agg[("tt_dec", t)] = np.zeros((L, 64), np.int64)
        agg[("tt_alarm", t)] = np.zeros((L, 64), np.int64)
    sab = {}
    sal = {}
    cand_f, cand_a = [], []
    t0 = time.time()
    with ProcessPoolExecutor(args.workers) as ex:
        for i, (key, r) in enumerate(ex.map(run_one, keys, chunksize=4)):
            agg["n"] += r["n"]
            agg["seizure_windows"] += r["seizure_windows"]
            agg["tt_hits"] += r["tt_hits"]
            for t in THRS:
                agg[("tt_dec", t)] += r["tt_dec"][t]
                agg[("tt_alarm", t)] += r["tt_alarm"][t]
            for d, src in ((sab, r["sab"]), (sal, r["sal"])):
                for k2, v in src.items():
                    d[k2] = d.get(k2, 0) + v
            cand_f.append(r["cand"][0]); cand_a.append(r["cand"][1])
            if (i + 1) % 100 == 0:
                print(f"{i + 1}/{len(keys)} recordings, {agg['n']:,} windows, {time.time() - t0:.0f} s", flush=True)
    # candidate pool for the self-test (one window per addressed entry per recording, plus random windows)
    feats_u = np.concatenate(cand_f).astype(np.int64)
    art_u = np.concatenate(cand_a)
    bits_u = (feats_u[:, M["bit_col"]] > M["bit_thr"]).astype(np.uint8)
    cnt = np.ones(len(feats_u), np.int64)
    u = bits_u
    print(f"{agg['n']:,} windows, {len(feats_u):,} candidate vectors, {time.time() - t0:.0f} s", flush=True)

    # ---------------------------------------------------------------- fault classes
    tt_obs = agg["tt_hits"] > 0
    sa_list = [("sab", i, v) for i in range(B) for v in (0, 1)] + [("sal", j, v) for j in range(L) for v in (0, 1)]
    sa_score = np.array([sab["score"][i, v] for _, i, v in sa_list[: 2 * B]] +
                        [sal["score"][j, v] for _, j, v in sa_list[2 * B:]])
    sa_obs = sa_score > 0

    def cls(t):
        dec_tt = agg[("tt_dec", t)] > 0
        al_tt = agg[("tt_alarm", t)] > 0
        dec_sa = np.array([sab[t][i, v] for _, i, v in sa_list[: 2 * B]] + [sal[t][j, v] for _, j, v in sa_list[2 * B:]]) > 0
        al_sa = np.array([sab[("a", t)][i, v] for _, i, v in sa_list[: 2 * B]] +
                         [sal[("a", t)][j, v] for _, j, v in sa_list[2 * B:]]) > 0
        return dec_tt, al_tt, dec_sa, al_sa

    # ---------------------------------------------------------------- current BIST ROM vectors
    from seizelut.hw.export import load_export
    bist = json.loads((REPO / "hw/kv260/rtl/seizelut_regs.json").read_text())["bist"]
    v = np.load(REPO / "hw/kv260/board/vectors" / f"{bist['recording']}.npz")
    w0 = int(bist["start_window"])
    rom_f = v["feats"][w0: w0 + int(bist["n"])].astype(np.int64)
    rom_bits = (rom_f[:, M["bit_col"]] > M["bit_thr"]).astype(np.uint8)
    rom_tt, rom_sa = coverage(M, rom_bits, tt_obs, sa_list, sa_obs)

    # ---------------------------------------------------------------- coverage-driven selection (training patterns)
    _, addr_u, _, score_u = forward_bits(M, bits_u)
    covered = np.zeros((L, 64), bool)
    chosen = []
    need = tt_obs.copy()
    # rarest entries first: for each uncovered entry, among the patterns that address it pick the one that covers
    # the most uncovered entries (ties: the most frequent pattern)
    ent = [(int(agg["tt_hits"][j, a]), j, a) for j in range(L) for a in range(64) if need[j, a]]
    ent.sort()
    for _, j, a in ent:
        if covered[j, a]:
            continue
        cand = np.nonzero(addr_u[:, j] == a)[0]
        gain = (~covered[np.arange(L)[None, :], addr_u[cand]]).sum(1)
        best = cand[np.lexsort((-cnt[cand], -gain))[0]]
        chosen.append(best)
        covered[np.arange(L), addr_u[best]] = True
    n_tt_sel = len(chosen)
    # stuck-at faults not yet seen: add the pattern that sees the most remaining ones
    D_sel = detects(M, bits_u[chosen], sa_list).any(0)
    remaining = np.nonzero(sa_obs & ~D_sel)[0]
    if len(remaining):
        rng = np.random.default_rng(0)
        pool = np.arange(len(u))
        Dp = detects(M, bits_u[pool], [sa_list[f] for f in remaining])
        left = np.ones(len(remaining), bool)
        while left.any():
            g = (Dp[:, left]).sum(1)
            if g.max() == 0:
                break
            b = int(np.argmax(g))
            chosen.append(int(pool[b]))
            left &= ~Dp[b]
    chosen = np.array(chosen)
    sel_tt, sel_sa = coverage(M, bits_u[chosen], tt_obs, sa_list, sa_obs)

    # ---------------------------------------------------------------- report
    def pct(a, b):
        return round(100.0 * a / b, 2) if b else None

    rep = {"what": "single-fault analysis of the deployed classifier on the 96 training patients (2,072 recordings)",
           "model": "export/n4_distill_s0", "windows": int(agg["n"]), "hours": round(agg["n"] / 3600, 1),
           "candidate_vectors": int(len(feats_u)),
           "faults": {"truth_table_bits": int(L * 64), "comparator_stuck_at": int(2 * B), "lut_output_stuck_at": int(2 * L)}}
    tt_tot = L * 64
    rep["truth_table"] = {"entries": tt_tot, "addressed_by_training_data": int(tt_obs.sum()),
                          "never_addressed": int(tt_tot - tt_obs.sum()),
                          "never_addressed_pct": pct(tt_tot - tt_obs.sum(), tt_tot),
                          "entries_addressed_fewer_than_10_times": int(((agg["tt_hits"] > 0) & (agg["tt_hits"] < 10)).sum()),
                          "per_lut_distinct_addresses_max": int(tt_obs.sum(1).max()),
                          "per_lut_distinct_addresses_median": float(np.median(tt_obs.sum(1)))}
    rep["operating_points"] = {}
    for t in THRS:
        dec_tt, al_tt, dec_sa, al_sa = cls(t)
        worst_tt = agg[("tt_dec", t)].max()
        sa_dec_counts = np.array([sab[t][i, v] for _, i, v in sa_list[: 2 * B]] + [sal[t][j, v] for _, j, v in sa_list[2 * B:]])
        rep["operating_points"][str(t)] = {
            "threshold": t,
            "decision_relevant": {"truth_table": int(dec_tt.sum()), "stuck_at": int(dec_sa.sum())},
            "alarm_relevant": {"truth_table": int(al_tt.sum()), "stuck_at": int(al_sa.sum())},
            "worst_truth_table_fault_decision_changes_pct": pct(worst_tt, agg["n"]),
            "worst_stuck_at_fault_decision_changes_pct": pct(sa_dec_counts.max(), agg["n"]),
            "median_relevant_truth_table_fault_decision_changes": float(np.median(agg[("tt_dec", t)][dec_tt])) if dec_tt.any() else 0,
            "rom_bist_detects": {"decision_relevant": pct((rom_tt & dec_tt).sum() + (rom_sa & dec_sa).sum(), dec_tt.sum() + dec_sa.sum()),
                                 "alarm_relevant": pct((rom_tt & al_tt).sum() + (rom_sa & al_sa).sum(), al_tt.sum() + al_sa.sum())},
            "selected_bist_detects": {"decision_relevant": pct((sel_tt & dec_tt).sum() + (sel_sa & dec_sa).sum(), dec_tt.sum() + dec_sa.sum()),
                                      "alarm_relevant": pct((sel_tt & al_tt).sum() + (sel_sa & al_sa).sum(), al_tt.sum() + al_sa.sum())}}
    obs_tot = int(tt_obs.sum() + sa_obs.sum())
    rep["observable_faults"] = {"truth_table": int(tt_obs.sum()), "stuck_at": int(sa_obs.sum()), "total": obs_tot,
                                "of_all_faults": int(L * 64 + 2 * B + 2 * L)}
    rep["rom_bist"] = {"vectors": int(len(rom_f)), "source": f"{bist['recording']} windows {w0}-{w0 + len(rom_f) - 1}",
                       "detects_observable_pct": pct((rom_tt & tt_obs).sum() + (rom_sa & sa_obs).sum(), obs_tot),
                       "detects_truth_table_observable_pct": pct((rom_tt & tt_obs).sum(), tt_obs.sum()),
                       "detects_stuck_at_observable_pct": pct((rom_sa & sa_obs).sum(), sa_obs.sum())}
    rep["selected_bist"] = {"vectors": int(len(chosen)), "for_truth_table": n_tt_sel,
                            "lower_bound_vectors": int(tt_obs.sum(1).max()),
                            "detects_observable_pct": pct((sel_tt & tt_obs).sum() + (sel_sa & sa_obs).sum(), obs_tot),
                            "detects_truth_table_observable_pct": pct((sel_tt & tt_obs).sum(), tt_obs.sum()),
                            "detects_stuck_at_observable_pct": pct((sel_sa & sa_obs).sum(), sa_obs.sum()),
                            "undetected_observable_stuck_at": [list(map(str, sa_list[f])) for f in np.nonzero(sa_obs & ~sel_sa)[0]],
                            "source": "windows of the 96 training patients (one per addressed truth-table entry per recording, plus 64 random per recording)"}
    # coverage as a function of the number of selected vectors (order of selection), truth-table part
    curve = []
    cov = np.zeros((L, 64), bool)
    for m, idx in enumerate(chosen, 1):
        cov[np.arange(L), addr_u[idx]] = True
        if m in (1, 2, 4, 8, 16, 32, 64, 96, 128, 192, 256) or m == len(chosen):
            curve.append([m, pct((cov & tt_obs).sum(), tt_obs.sum())])
    rep["selected_bist"]["truth_table_coverage_curve"] = curve
    OUT.write_text(json.dumps(rep, indent=1))
    SEL.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(SEL, feats=feats_u[chosen], art=art_u[chosen], bits=bits_u[chosen], count=cnt[chosen],
                        score=score_u[chosen])
    np.savez_compressed(SEL.parent / "fault_counts.npz", tt_hits=agg["tt_hits"],
                        **{f"tt_dec_{t}": agg[("tt_dec", t)] for t in THRS},
                        **{f"tt_alarm_{t}": agg[("tt_alarm", t)] for t in THRS},
                        sab_score=sab["score"], sal_score=sal["score"],
                        **{f"sab_dec_{t}": sab[t] for t in THRS}, **{f"sab_alarm_{t}": sab[("a", t)] for t in THRS},
                        **{f"sal_dec_{t}": sal[t] for t in THRS}, **{f"sal_alarm_{t}": sal[("a", t)] for t in THRS})
    print(json.dumps({k: rep[k] for k in ("truth_table", "observable_faults", "rom_bist", "selected_bist")}, indent=1)[:3000])
    print(json.dumps(rep["operating_points"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
