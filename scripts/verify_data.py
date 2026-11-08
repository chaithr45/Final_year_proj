#!/usr/bin/env python3
"""Check a local SeizeIT2 copy against the committed audit (reports/data_audit.json).

Counts subjects, runs and files per modality, checks that every sidecar has its
EDF (unless --metadata-only), and that sampling rates in sidecars match the EDF
headers. Exit code 0 = the tree matches the audit.

Usage:
  python scripts/verify_data.py                       # full download in data/raw/ds005873
  python scripts/verify_data.py --metadata-only       # tree from scripts/fetch_metadata.py
  python scripts/verify_data.py --root tests/fixtures/synthetic_bids --expected tests/fixtures/expected_counts.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from seizelut.data.bids import MODALITIES, discover_runs

REPO = Path(__file__).resolve().parents[1]


def count_tree(root: Path, metadata_only: bool) -> tuple[dict, list[str]]:
    runs = discover_runs(root)
    problems = []
    n_edf = Counter()
    n_side = Counter()
    fs = Counter()
    for r in runs:
        if r.events is None:
            problems.append(f"{r.key}: missing _events.tsv")
        for m in r.modalities:
            if m not in r.sidecar:
                problems.append(f"{r.key}: {m} EDF without sidecar")
                continue
            n_side[m] += 1
            if m in r.edf:
                n_edf[m] += 1
                side_fs = r.read_sidecar(m)["SamplingFrequency"]
                h = r.read_header(m)
                rates = {h.sampling_rate(lb) for lb in h.labels}
                if rates != {float(side_fs)}:
                    problems.append(f"{r.key}: {m} sidecar says {side_fs} Hz, EDF says {sorted(rates)}")
                fs[f"{m}|{side_fs}|{'|'.join(f'{v:g}' for v in sorted(rates))}"] += 1
            elif not metadata_only:
                problems.append(f"{r.key}: {m} sidecar without EDF")
    counts = {"n_subjects": len({r.subject for r in runs}), "n_runs": {m: n_side[m] for m in MODALITIES},
              "n_edf": {m: n_edf[m] for m in MODALITIES}, "subjects": sorted({r.subject for r in runs})}
    if fs:
        counts["fs_counts"] = dict(sorted(fs.items()))
    return counts, problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(REPO / "data/raw/ds005873"))
    ap.add_argument("--expected", default=str(REPO / "reports/data_audit.json"))
    ap.add_argument("--metadata-only", action="store_true", help="EDF files are not expected locally")
    args = ap.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"{root} does not exist; run scripts/download_data.sh first", file=sys.stderr)
        return 2
    got, problems = count_tree(root, args.metadata_only)
    exp = json.loads(Path(args.expected).read_text())

    def check(name, a, b):
        ok = a == b
        print(f"[{'ok' if ok else 'MISMATCH'}] {name}: found {a}" + ("" if ok else f", audit says {b}"))
        return ok

    ok = check("subjects", got["n_subjects"], exp["n_subjects"])
    same_ids = got["subjects"] == exp["subjects"]
    print(f"[{'ok' if same_ids else 'MISMATCH'}] subject ids" + ("" if same_ids else
          f": missing {sorted(set(exp['subjects']) - set(got['subjects']))}, extra {sorted(set(got['subjects']) - set(exp['subjects']))}"))
    ok &= same_ids
    for m in MODALITIES:
        ok &= check(f"{m} runs (sidecars)", got["n_runs"][m], exp["n_runs"][m])
        if not args.metadata_only:
            ok &= check(f"{m} EDF files", got["n_edf"][m], exp["n_runs"][m])
    if "fs_counts" in got and not args.metadata_only:
        ok &= check("sampling rates (modality|sidecar|edf: files)", got["fs_counts"], exp["fs_counts"])
    for p in problems[:50]:
        print("  problem:", p)
    if len(problems) > 50:
        print(f"  ... {len(problems) - 50} more problems")
    ok &= not problems
    print("VERIFIED" if ok else "NOT VERIFIED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
