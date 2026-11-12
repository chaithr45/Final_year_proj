#!/usr/bin/env python3
"""Zip the KV260 kit for the user: dist/SeizeLUT_KV260_kit_<version>.zip (sources, scripts, model, vectors,
verification results; no build outputs). If out/seizelut.bit and out/seizelut.hwh exist they are added to
board/ in the zip, so the board folder can be copied as is.
Usage: python tools/make_kit_zip.py [--version v1]
"""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {"build", "out", "dist", "__pycache__", ".ipynb_checkpoints"}
SKIP_FILES = {"libfastio.so"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", default="v1")
    v = ap.parse_args().version
    dist = KIT / "dist"
    dist.mkdir(exist_ok=True)
    z = dist / f"SeizeLUT_KV260_kit_{v}.zip"
    root = f"seizelut_kv260_{v}"
    n = 0
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(KIT.rglob("*")):
            rel = p.relative_to(KIT)
            if p.is_dir() or set(rel.parts) & SKIP_DIRS or p.name in SKIP_FILES:
                continue
            if rel.parts[:2] == ("board", "results") or rel.as_posix() == "board/frontend/libseizelut_fe.so":
                continue
            if rel.parts[:2] == ("sim", "vectors") and p.name != "sub-097_run-10.hex":
                continue
            zf.write(p, f"{root}/{rel.as_posix()}")
            n += 1
        for f in ("seizelut.bit", "seizelut.hwh"):
            if (KIT / "out" / f).exists():
                zf.write(KIT / "out" / f, f"{root}/board/{f}")
                n += 1
    print(f"{z} ({n} files, {z.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
