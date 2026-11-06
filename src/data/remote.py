"""Use a local EDF if present, otherwise stream it from the public OpenNeuro bucket.

Lets every extraction script run on a machine without the 126 GB copy:
    with local_edf(run, "eeg") as path: data = read_edf(path)
"""
from __future__ import annotations

import contextlib
import os
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

BUCKET = "https://s3.amazonaws.com/openneuro.org/ds005873"


def _download(url: str, dest: Path, retries: int = 4) -> None:
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=120) as resp, open(dest, "wb") as fh:
                while chunk := resp.read(1 << 22):
                    fh.write(chunk)
            return
        except Exception:
            if attempt == retries:
                raise
            time.sleep(2 ** (attempt + 1))


@contextlib.contextmanager
def local_edf(run, modality: str, tmp_dir: str | os.PathLike | None = None):
    """Yield a local path to the run's EDF for `modality`; temporary downloads are deleted."""
    if modality in run.edf and Path(run.edf[modality]).exists():
        yield Path(run.edf[modality])
        return
    side = run.sidecar[modality]
    rel = side.relative_to(run.root).with_suffix(".edf")
    with tempfile.TemporaryDirectory(dir=tmp_dir) as tmp:
        dest = Path(tmp) / rel.name
        _download(f"{BUCKET}/{urllib.parse.quote(str(rel))}", dest)
        yield dest
