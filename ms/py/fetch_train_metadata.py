#!/usr/bin/env python3
"""Mirror the SeizeIT2 metadata of the 96 TRAINING patients only (sub-001..sub-096).

Same source and layout as scripts/fetch_metadata.py (public OpenNeuro S3 bucket, BIDS tree under
data/raw/ds005873/), but restricted to training subjects, so the mixed-signal study never downloads a
test patient's annotations (ground rule 2). Fetches the top-level files and every sidecar .json and
_events.tsv; signals are streamed later by scripts/extract_features.py.

Usage: python ms/py/fetch_train_metadata.py [--root data/raw/ds005873] [--workers 16]
"""
from __future__ import annotations

import argparse
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from seizelut.data.split import official_train_subjects  # noqa: E402

BUCKET = "https://s3.amazonaws.com/openneuro.org"
PREFIX = "ds005873/"
TOP = ["dataset_description.json", "participants.json", "README", "CHANGES"]
NS = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}


def get(url: str, retries: int = 4) -> bytes:
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read()
        except Exception:
            if attempt == retries:
                raise
            time.sleep(2 ** (attempt + 1))
    raise AssertionError


def list_keys(prefix: str) -> list[str]:
    keys, token = [], None
    while True:
        q = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
        if token:
            q["continuation-token"] = token
        root = ET.fromstring(get(f"{BUCKET}?{urllib.parse.urlencode(q)}"))
        keys += [c.find("s:Key", NS).text for c in root.findall("s:Contents", NS)]
        if root.find("s:IsTruncated", NS).text != "true":
            return keys
        token = root.find("s:NextContinuationToken", NS).text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(REPO / "data/raw/ds005873"))
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()
    root = Path(args.root)
    subjects = official_train_subjects()
    assert subjects[0] == "sub-001" and subjects[-1] == "sub-096" and len(subjects) == 96
    with ThreadPoolExecutor(args.workers) as pool:
        listed = list(pool.map(lambda s: list_keys(f"{PREFIX}{s}/"), subjects))
    keys = [PREFIX + t for t in TOP]
    keys += [k for ks in listed for k in ks if k.endswith(".json") or k.endswith("_events.tsv")]
    for k in keys:   # guard: nothing outside the training subjects
        part = k[len(PREFIX):].split("/")[0]
        assert part in TOP or part in subjects, k

    def fetch(k: str) -> str:
        dest = root / k[len(PREFIX):]
        if dest.exists():
            return "skip"
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = get(f"{BUCKET}/{urllib.parse.quote(k)}")
        except Exception as exc:          # optional top-level files may not exist
            if k[len(PREFIX):] in TOP:
                return "missing"
            raise exc
        dest.write_bytes(data)
        return "ok"

    with ThreadPoolExecutor(args.workers) as pool:
        res = list(pool.map(fetch, keys))
    print(f"{len(keys)} files: {res.count('ok')} fetched, {res.count('skip')} already present, "
          f"{res.count('missing')} optional top-level files absent; subjects {subjects[0]}..{subjects[-1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
