#!/usr/bin/env python3
"""Fetch SeizeIT2 metadata without downloading the 126 GB of signals.

Downloads from the public OpenNeuro S3 bucket (plain HTTPS, no account):
  * every sidecar .json, every _events.tsv and the top-level files, mirrored into
    data/raw/ds005873/ so the BIDS loader works on a metadata-only tree;
  * the header of every .edf (HTTP range request) into cache/edf_headers/;
  * the full object listing with sizes into cache/s3_listing.json.

Usage:  python scripts/fetch_metadata.py [--root data/raw/ds005873] [--workers 32]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BUCKET = "https://s3.amazonaws.com/openneuro.org"
PREFIX = "ds005873/"
HEADER_BYTES = 8192  # enough for an EDF header with up to 31 signals
_NS = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}


def list_objects(prefix: str = PREFIX) -> list[tuple[str, int]]:
    out, token = [], None
    while True:
        q = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
        if token:
            q["continuation-token"] = token
        root = ET.fromstring(_get(f"{BUCKET}?{urllib.parse.urlencode(q)}"))
        out += [(c.find("s:Key", _NS).text, int(c.find("s:Size", _NS).text)) for c in root.findall("s:Contents", _NS)]
        if root.find("s:IsTruncated", _NS).text != "true":
            return out
        token = root.find("s:NextContinuationToken", _NS).text


def _get(url: str, byte_range: str | None = None, retries: int = 4) -> bytes:
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"Range": f"bytes={byte_range}"} if byte_range else {})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except Exception:
            if attempt == retries:
                raise
            time.sleep(2 ** (attempt + 1))
    raise AssertionError


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default="data/raw/ds005873")
    ap.add_argument("--headers", default="cache/edf_headers")
    ap.add_argument("--listing", default="cache/s3_listing.json")
    ap.add_argument("--workers", type=int, default=32)
    args = ap.parse_args()

    root, hdr_dir = Path(args.root), Path(args.headers)
    listing = list_objects()
    Path(args.listing).parent.mkdir(parents=True, exist_ok=True)
    Path(args.listing).write_text(json.dumps([{"key": k, "size": s} for k, s in listing]))
    print(f"{len(listing)} objects, {sum(s for _, s in listing) / 1e9:.2f} GB", flush=True)

    jobs = []
    for key, size in listing:
        rel = key[len(PREFIX):]
        if not rel or rel.endswith("/"):
            continue
        if rel.endswith(".edf"):
            jobs.append((key, hdr_dir / (rel + ".hdr"), f"0-{HEADER_BYTES - 1}"))
        else:
            jobs.append((key, root / rel, None))
    todo = [j for j in jobs if not j[1].exists()]
    print(f"{len(todo)} of {len(jobs)} files to fetch", flush=True)

    def fetch(job):
        key, dest, rng = job
        data = _get(f"{BUCKET}/{urllib.parse.quote(key)}", rng)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(dest)

    failed = 0
    with ThreadPoolExecutor(args.workers) as pool:
        futures = {pool.submit(fetch, j): j for j in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            if fut.exception():
                failed += 1
                print(f"FAILED {futures[fut][0]}: {fut.exception()}", file=sys.stderr)
            if i % 1000 == 0:
                print(f"  {i}/{len(todo)}", flush=True)
    print(f"done, {failed} failures", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
