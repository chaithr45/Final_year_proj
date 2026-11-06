"""SeizeIT2 `_events.tsv` annotations (BIDS-score format, see events.json)."""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass

# eventType values that are not seizures (events.json).
NON_SEIZURE_TYPES = {"bckg", "impd"}

# Coarse seizure classes used for the per-type breakdowns (Section 7.4).
SEIZURE_CLASSES = ("FA", "FIA", "FBTC", "focal_unknown_awareness", "unknown_onset", "generalized", "unclassified")


def seizure_class(event_type: str) -> str:
    """Map an ILAE-2017 eventType string (events.json levels) to a coarse class."""
    t = event_type
    if t.startswith("sz_foc_f2b"):
        return "FBTC"
    if t.startswith("sz_foc_ia"):
        return "FIA"
    if t.startswith("sz_foc_a"):
        return "FA"
    if t.startswith("sz_foc"):            # sz_foc, sz_foc_ua_*
        return "focal_unknown_awareness"
    if t.startswith("sz_uo"):
        return "unknown_onset"
    if t.startswith("sz_gen"):
        return "generalized"
    if t == "sz":
        return "unclassified"
    raise ValueError(f"not a seizure eventType: {event_type!r}")


def _float_or_none(text: str) -> float | None:
    text = text.strip()
    if text in ("", "n/a", "nan", "NaN"):
        return None
    return float(text)


@dataclass(frozen=True)
class Event:
    onset: float           # seconds from the start of the run
    duration: float        # seconds
    event_type: str
    lateralization: str
    localization: str
    vigilance: str
    confidence: float | None
    channels: str          # "channels where visible" -- NEVER a model input (Section 7.2)

    @property
    def end(self) -> float:
        return self.onset + self.duration

    @property
    def is_seizure(self) -> bool:
        return self.event_type not in NON_SEIZURE_TYPES

    @property
    def is_impedance_check(self) -> bool:
        return self.event_type == "impd"


@dataclass(frozen=True)
class RunAnnotations:
    events: tuple[Event, ...]
    recording_duration: float | None   # the tsv's recordingDuration column (seconds)

    @property
    def seizures(self) -> list[Event]:
        return [e for e in self.events if e.is_seizure]

    @property
    def impedance_checks(self) -> list[Event]:
        return [e for e in self.events if e.is_impedance_check]

    def seizure_intervals(self) -> list[tuple[float, float]]:
        """Merged, sorted (start, end) seizure intervals in seconds."""
        return merge_intervals([(e.onset, e.end) for e in self.seizures])


def merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[list[float]] = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def read_events(path: str | os.PathLike) -> RunAnnotations:
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    events = []
    rec_dur = None
    for r in rows:
        rec_dur = _float_or_none(r.get("recordingDuration", "")) or rec_dur
        events.append(Event(
            onset=float(r["onset"]),
            duration=float(r["duration"]),
            event_type=r["eventType"].strip(),
            lateralization=r.get("lateralization", "n/a").strip(),
            localization=r.get("localization", "n/a").strip(),
            vigilance=r.get("vigilance", "n/a").strip(),
            confidence=_float_or_none(r.get("confidence", "")),
            channels=r.get("channels", "n/a").strip(),
        ))
    return RunAnnotations(events=tuple(events), recording_duration=rec_dur)
