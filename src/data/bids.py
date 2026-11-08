"""Discover and load SeizeIT2 runs from a BIDS tree.

Layout (ds005873 v1.1.0):
    sub-XXX/ses-01/{eeg,ecg,emg,mov}/sub-XXX_ses-01_task-szMonitoring_run-YY_<mod>.{edf,json}
    sub-XXX/ses-01/eeg/sub-XXX_ses-01_task-szMonitoring_run-YY_events.tsv

Sampling rates and channel names are always read from the files, never assumed
(Section 3.1).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .edf import EdfData, EdfHeader, read_edf, read_header
from .events import RunAnnotations, read_events

MODALITIES = ("eeg", "ecg", "emg", "mov")
_RUN_RE = re.compile(r"^(sub-\d+)_(ses-[^_]+)_task-([^_]+)_(run-\d+)_(eeg|ecg|emg|mov|events)\.(edf|json|tsv)$")


@dataclass
class Run:
    """One continuous recording file set. Windows never cross a run boundary."""

    root: Path
    subject: str          # "sub-001"
    session: str          # "ses-01"
    task: str
    run: str              # "run-01"
    edf: dict[str, Path] = field(default_factory=dict)       # modality -> .edf
    sidecar: dict[str, Path] = field(default_factory=dict)   # modality -> .json
    events: Path | None = None

    @property
    def key(self) -> str:
        return f"{self.subject}_{self.run}"

    @property
    def subject_number(self) -> int:
        return int(self.subject.split("-")[1])

    @property
    def modalities(self) -> list[str]:
        """Modalities whose sidecar exists (the EDF may be absent in a metadata-only tree)."""
        return [m for m in MODALITIES if m in self.sidecar or m in self.edf]

    def has(self, modality: str) -> bool:
        return modality in self.modalities

    def read_sidecar(self, modality: str) -> dict:
        with open(self.sidecar[modality], encoding="utf-8") as fh:
            return json.load(fh)

    def read_annotations(self) -> RunAnnotations:
        if self.events is None:
            raise FileNotFoundError(f"{self.key}: no _events.tsv")
        return read_events(self.events)

    def read_header(self, modality: str) -> EdfHeader:
        return read_header(self.edf[modality])

    def read_signals(self, modality: str, labels: list[str] | None = None) -> EdfData:
        return read_edf(self.edf[modality], labels)


def discover_runs(root: str | os.PathLike, subjects: list[str] | None = None) -> list[Run]:
    """Find every run under `root`, sorted by subject and run.

    A run is identified by its EEG sidecar or EDF (every patient has EEG); other
    modalities attach to it when present.
    """
    root = Path(root)
    runs: dict[tuple[str, str], Run] = {}
    sub_dirs = sorted(p for p in root.glob("sub-*") if p.is_dir())
    if subjects is not None:
        wanted = set(subjects)
        sub_dirs = [p for p in sub_dirs if p.name in wanted]
    for sub_dir in sub_dirs:
        for f in sorted(sub_dir.glob("ses-*/*/*")):
            m = _RUN_RE.match(f.name)
            if not m:
                continue
            subject, session, task, run_id, kind, ext = m.groups()
            if f.parent.name != (kind if kind != "events" else "eeg"):
                continue
            r = runs.setdefault((subject, run_id), Run(root, subject, session, task, run_id))
            if kind == "events":
                r.events = f
            elif ext == "edf":
                r.edf[kind] = f
            elif ext == "json":
                r.sidecar[kind] = f
    return [runs[k] for k in sorted(runs)]


def subjects_in(runs: list[Run]) -> list[str]:
    return sorted({r.subject for r in runs})
