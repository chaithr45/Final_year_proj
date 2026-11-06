"""Statistics of Section 7.5: paired Wilcoxon, Friedman, bootstrap CIs over patients."""
from __future__ import annotations

import numpy as np


def paired_wilcoxon(a, b) -> dict:
    """Two-sided Wilcoxon signed-rank test on per-patient values (NaN pairs dropped)."""
    from scipy.stats import wilcoxon
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = ~(np.isnan(a) | np.isnan(b))
    a, b = a[ok], b[ok]
    d = a - b
    if np.all(d == 0) or len(d) < 2:
        return {"n": int(len(d)), "median_diff": float(np.median(d)) if len(d) else float("nan"), "p": 1.0}
    res = wilcoxon(a, b, zero_method="wilcox", alternative="two-sided")
    return {"n": int(len(d)), "median_diff": float(np.median(d)), "statistic": float(res.statistic), "p": float(res.pvalue)}


def friedman(*per_model_values) -> dict:
    from scipy.stats import friedmanchisquare
    m = np.array(per_model_values, dtype=float)
    m = m[:, ~np.isnan(m).any(axis=0)]
    res = friedmanchisquare(*m)
    return {"n": int(m.shape[1]), "k": int(m.shape[0]), "statistic": float(res.statistic), "p": float(res.pvalue)}


def bootstrap_ci(values, stat=np.nanmean, n_boot: int = 10000, alpha: float = 0.05, seed: int = 0) -> dict:
    """Percentile bootstrap CI, resampling patients with replacement."""
    v = np.asarray(values, float)
    v = v[~np.isnan(v)]
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(v), size=(n_boot, len(v)))
    boots = np.array([stat(v[i]) for i in idx])
    return {"estimate": float(stat(v)), "low": float(np.quantile(boots, alpha / 2)),
            "high": float(np.quantile(boots, 1 - alpha / 2)), "n": int(len(v))}
