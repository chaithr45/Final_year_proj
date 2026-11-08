#!/usr/bin/env python3
"""Write the Tier-2 configs (N2, N4, N5, N6; Section 6.3) as one change each on top of a base DWN config.

Every method is compared with its own baseline: the base run (same features, size, epochs, data
and seed), with a paired Wilcoxon test on the per-patient inner-fold results (Section 6.6).
  N2 encoders      uniform, gaussian, learned thresholds (two comparator penalties)
  N4 teacher       distillation from LightGBM, teacher-guided hard negatives, both
  N5 training      focal, generalized CE, symmetric CE, seizure-level MIL (top-50 %), onset weight x3
  N6 fusion        EEG only, modality dropout, gated (quality/presence bits always in + dropout),
                   late fusion (one DWN per modality, same total LUTs)
Usage:  python scripts/make_m5_configs.py --base configs/m4/sweep/dwn_L200_b8_learn.yaml
Output: configs/m5/<method>.yaml (the base config's name is recorded in each file)
"""
from __future__ import annotations

import argparse
import copy
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
LGBM = yaml.safe_load((REPO / "configs/m4/lgbm.yaml").read_text())["model"]
GATE_BITS = ["present_ecg", "present_emg", "present_mov_acc", "present_mov_gyr", "ecg_quality_bad"]


def variants(base: dict) -> dict:
    p = base["model"]["params"]
    L = sum(p["layers"][:1])
    v = {
        "n2_uniform": {"params": {"encoder": "uniform"}},
        "n2_gaussian": {"params": {"encoder": "gaussian"}},
        "n2_learned": {"params": {"encoder": "learned", "comparator_penalty": 1e-4}},
        "n2_learned_p1e3": {"params": {"encoder": "learned", "comparator_penalty": 1e-3}},
        "n4_distill": {"params": {"distill_alpha": 0.5, "distill_T": 2.0}, "train": {"distill": {"teacher": LGBM}}},
        "n4_hardneg_teacher": {"train": {"hard_negative": {"by": "teacher", "top_fraction": 0.001, "teacher": LGBM}}},
        "n4_distill_hardneg": {"params": {"distill_alpha": 0.5, "distill_T": 2.0},
                               "train": {"distill": {"teacher": LGBM},
                                         "hard_negative": {"by": "teacher", "top_fraction": 0.001, "teacher": LGBM}}},
        "n5_focal": {"params": {"loss": "focal"}},
        "n5_gce": {"params": {"loss": "gce"}},
        "n5_sce": {"params": {"loss": "sce"}},
        "n5_mil": {"params": {"mil_topk": 0.5}},
        "n5_onset": {"params": {"onset_weight": 3.0}},
        "n6_eeg_only": {"features": {"include_prefix": ["eeg_"], "mi_top": base["features"]["mi_top"]}},
        "n6_dropout": {"train": {"modality_dropout": 0.2}},
        "n6_gated": {"features": {**base["features"], "always": GATE_BITS}, "train": {"modality_dropout": 0.2}},
        "n6_late": {"type": "dwn_late", "features": "all",
                    "params": {"layers": None, "groups": {
                        "eeg": {"prefix": ["eeg_"], "mi_top": 30, "layers": [round(0.6 * L)]},
                        "ecg": {"prefix": ["ecg_", "present_ecg"], "layers": [round(0.1 * L)]},
                        "emg": {"prefix": ["emg_", "present_emg"], "layers": [round(0.15 * L)]},
                        "mov": {"prefix": ["mov_", "present_mov_acc", "present_mov_gyr"], "layers": [round(0.15 * L)]}}}},
    }
    out = {}
    for name, ch in v.items():
        c = copy.deepcopy(base)
        c["name"] = name
        c["base_config"] = base["name"]
        if "type" in ch:
            c["model"]["type"] = ch["type"]
        for k, val in ch.get("params", {}).items():
            if val is None:
                c["model"]["params"].pop(k, None)
            else:
                c["model"]["params"][k] = val
        if "features" in ch:
            c["features"] = ch["features"]
        c.setdefault("train", {}).update(ch.get("train", {}))
        out[name] = c
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", default=str(REPO / "configs" / "m5"))
    args = ap.parse_args()
    base = yaml.safe_load(Path(args.base).read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, c in variants(base).items():
        (out / f"{name}.yaml").write_text(f"# Tier-2 variant of {base['name']} (scripts/make_m5_configs.py)\n"
                                          + yaml.safe_dump(c, sort_keys=False))
    print(f"{len(variants(base))} configs in {out}, base {base['name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
