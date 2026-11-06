"""Minimal, dependency-free EDF/EDF+ reader and writer.

Why our own reader: the integer pipeline (Section 5) starts from the raw 16-bit
digital samples, so we want them untouched, plus the exact digital->physical
gain from the header. The reader can also parse a header from bytes alone, which
lets the audit read every file's header with an HTTP range request instead of
downloading 126 GB. Tests cross-check it against pyEDFlib.

Format reference: Kemp et al. 1992 (EDF) and Kemp & Olivan 2003 (EDF+).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ANNOTATION_LABEL = "EDF Annotations"

# (name, width) of the per-signal header fields, in file order.
_SIGNAL_FIELDS = (
    ("label", 16),
    ("transducer", 80),
    ("physical_dim", 8),
    ("physical_min", 8),
    ("physical_max", 8),
    ("digital_min", 8),
    ("digital_max", 8),
    ("prefilter", 80),
    ("samples_per_record", 8),
    ("reserved", 32),
)


@dataclass(frozen=True)
class EdfSignalHeader:
    label: str
    transducer: str
    physical_dim: str
    physical_min: float
    physical_max: float
    digital_min: int
    digital_max: int
    prefilter: str
    samples_per_record: int

    @property
    def is_annotation(self) -> bool:
        return self.label == ANNOTATION_LABEL

    @property
    def gain(self) -> float:
        """Physical units per digital LSB."""
        return (self.physical_max - self.physical_min) / (self.digital_max - self.digital_min)

    @property
    def offset(self) -> float:
        """Physical value of digital 0."""
        return self.physical_min - self.gain * self.digital_min


@dataclass(frozen=True)
class EdfHeader:
    version: str
    patient_id: str
    recording_id: str
    start_date: str
    start_time: str
    header_bytes: int
    reserved: str
    n_records: int          # as written in the header (-1 = unknown)
    record_duration: float  # seconds
    signals: tuple[EdfSignalHeader, ...]

    @property
    def is_edf_plus(self) -> bool:
        return self.reserved.startswith("EDF+")

    @property
    def is_discontinuous(self) -> bool:
        return self.reserved.startswith("EDF+D")

    @property
    def record_samples(self) -> int:
        return sum(s.samples_per_record for s in self.signals)

    @property
    def record_bytes(self) -> int:
        return 2 * self.record_samples

    @property
    def data_signals(self) -> list[EdfSignalHeader]:
        return [s for s in self.signals if not s.is_annotation]

    @property
    def labels(self) -> list[str]:
        return [s.label for s in self.data_signals]

    def sampling_rate(self, label: str) -> float:
        sig = self.signal(label)
        return sig.samples_per_record / self.record_duration

    def signal(self, label: str) -> EdfSignalHeader:
        for s in self.signals:
            if s.label == label:
                return s
        raise KeyError(f"no signal {label!r}; have {[s.label for s in self.signals]}")

    @property
    def duration_s(self) -> float:
        """Nominal duration from the header (records x record duration)."""
        return self.n_records * self.record_duration


def parse_header(raw: bytes) -> EdfHeader:
    """Parse an EDF header from the first bytes of a file.

    `raw` must hold at least 256 + 256 * n_signals bytes.
    """
    if len(raw) < 256:
        raise ValueError("EDF header needs at least 256 bytes")
    fixed = raw[:256].decode("latin-1")
    n_signals = int(fixed[252:256])
    need = 256 + 256 * n_signals
    if len(raw) < need:
        raise ValueError(f"EDF header with {n_signals} signals needs {need} bytes, got {len(raw)}")
    var = raw[256:need].decode("latin-1")

    values: dict[str, list[str]] = {}
    pos = 0
    for name, width in _SIGNAL_FIELDS:
        values[name] = [var[pos + i * width: pos + (i + 1) * width].strip() for i in range(n_signals)]
        pos += width * n_signals

    signals = tuple(
        EdfSignalHeader(
            label=values["label"][i],
            transducer=values["transducer"][i],
            physical_dim=values["physical_dim"][i],
            physical_min=float(values["physical_min"][i]),
            physical_max=float(values["physical_max"][i]),
            digital_min=int(values["digital_min"][i]),
            digital_max=int(values["digital_max"][i]),
            prefilter=values["prefilter"][i],
            samples_per_record=int(values["samples_per_record"][i]),
        )
        for i in range(n_signals)
    )
    return EdfHeader(
        version=fixed[0:8].strip(),
        patient_id=fixed[8:88].strip(),
        recording_id=fixed[88:168].strip(),
        start_date=fixed[168:176].strip(),
        start_time=fixed[176:184].strip(),
        header_bytes=int(fixed[184:192]),
        reserved=fixed[192:236].strip(),
        n_records=int(fixed[236:244]),
        record_duration=float(fixed[244:252]),
        signals=signals,
    )


def read_header(path: str | os.PathLike) -> EdfHeader:
    with open(path, "rb") as fh:
        first = fh.read(256)
        n_signals = int(first[252:256].decode("latin-1"))
        rest = fh.read(256 * n_signals)
    return parse_header(first + rest)


@dataclass
class EdfData:
    """Digital samples of the data signals of one EDF file."""

    header: EdfHeader
    digital: dict[str, np.ndarray]      # label -> int16 samples
    fs: dict[str, float]                 # label -> sampling rate (Hz)
    n_records_read: int                  # records actually present in the file
    warnings: list[str] = field(default_factory=list)

    @property
    def labels(self) -> list[str]:
        return list(self.digital)

    def physical(self, label: str) -> np.ndarray:
        """Samples in physical units (float64), using the header gain/offset."""
        sig = self.header.signal(label)
        return self.digital[label].astype(np.float64) * sig.gain + sig.offset

    @property
    def duration_s(self) -> float:
        return self.n_records_read * self.header.record_duration


def _records_in_file(path: Path, header: EdfHeader) -> tuple[int, list[str]]:
    warnings = []
    data_bytes = path.stat().st_size - header.header_bytes
    n_full, remainder = divmod(data_bytes, header.record_bytes)
    if remainder:
        warnings.append(f"{remainder} trailing bytes after {n_full} full records")
    if header.n_records >= 0 and header.n_records != n_full:
        warnings.append(f"header says {header.n_records} records, file holds {n_full}")
    n = n_full if header.n_records < 0 else min(n_full, header.n_records)
    return n, warnings


def _record_matrix(path: Path, header: EdfHeader, n_records: int) -> np.ndarray:
    return np.memmap(
        path, dtype="<i2", mode="r", offset=header.header_bytes,
        shape=(n_records, header.record_samples),
    )


def read_edf(path: str | os.PathLike, labels: list[str] | None = None) -> EdfData:
    """Read the int16 digital samples of the requested data signals.

    Annotation signals are skipped. `labels=None` reads every data signal.
    """
    path = Path(path)
    header = read_header(path)
    n_records, warnings = _records_in_file(path, header)
    wanted = header.labels if labels is None else list(labels)
    missing = [lb for lb in wanted if lb not in header.labels]
    if missing:
        raise KeyError(f"{path.name}: signals {missing} not found; have {header.labels}")

    mat = _record_matrix(path, header, n_records)
    digital, fs = {}, {}
    start = 0
    for sig in header.signals:
        stop = start + sig.samples_per_record
        if sig.label in wanted:
            digital[sig.label] = np.ascontiguousarray(mat[:, start:stop]).reshape(-1)
            fs[sig.label] = sig.samples_per_record / header.record_duration
        start = stop
    del mat
    return EdfData(header=header, digital=digital, fs=fs, n_records_read=n_records, warnings=warnings)


_TAL_ONSET = re.compile(rb"^([+-]\d+(?:\.\d*)?)\x14\x14")


def record_onsets(path: str | os.PathLike) -> np.ndarray | None:
    """Start time (s) of every data record, from the EDF+ time-keeping annotations.

    Returns None for plain EDF. For EDF+C this should be 0, d, 2d, ...; for EDF+D
    it reveals the gaps inside the file.
    """
    path = Path(path)
    header = read_header(path)
    if not header.is_edf_plus:
        return None
    ann_idx = [i for i, s in enumerate(header.signals) if s.is_annotation]
    if not ann_idx:
        return None
    n_records, _ = _records_in_file(path, header)
    mat = _record_matrix(path, header, n_records)
    start = sum(s.samples_per_record for s in header.signals[: ann_idx[0]])
    width = header.signals[ann_idx[0]].samples_per_record
    raw = np.ascontiguousarray(mat[:, start:start + width]).view(np.uint8)
    onsets = np.full(n_records, np.nan)
    for r in range(n_records):
        m = _TAL_ONSET.match(raw[r].tobytes())
        if m:
            onsets[r] = float(m.group(1))
    return onsets


# --------------------------------------------------------------------------- writer

def _field(value: object, width: int) -> bytes:
    text = str(value)
    if len(text) > width:
        raise ValueError(f"{text!r} does not fit in {width} characters")
    return text.ljust(width).encode("latin-1")


def _num(value: float, width: int = 8) -> bytes:
    """Format a number to fit an 8-character EDF field."""
    if float(value).is_integer():
        return _field(int(value), width)
    text = f"{value:.{width}g}"
    while len(text) > width:
        text = text[:-1]
    return _field(text, width)


@dataclass
class EdfSignal:
    label: str
    digital: np.ndarray           # int16 samples
    fs: int                       # samples per second (record duration is 1 s)
    physical_min: float
    physical_max: float
    physical_dim: str = "uV"
    digital_min: int = -32768
    digital_max: int = 32767


def write_edf(path: str | os.PathLike, signals: list[EdfSignal], *, edf_plus: bool = True,
              patient_id: str = "X X X X", recording_id: str = "Startdate 01-JAN-2000 X X X",
              start_date: str = "01.01.00", start_time: str = "00.00.00") -> None:
    """Write an EDF(+C) file with 1-second records. Used for synthetic test fixtures."""
    n_records = None
    for s in signals:
        if len(s.digital) % s.fs:
            raise ValueError(f"{s.label}: {len(s.digital)} samples is not a whole number of seconds")
        n = len(s.digital) // s.fs
        if n_records is not None and n != n_records:
            raise ValueError("all signals must cover the same number of seconds")
        n_records = n
    assert n_records is not None

    ann_samples = 30  # 60 bytes per record is plenty for "+<onset>\x14\x14\x00"
    hdr_signals = [
        (s.label, "", s.physical_dim, s.physical_min, s.physical_max, s.digital_min, s.digital_max, "", s.fs)
        for s in signals
    ]
    if edf_plus:
        hdr_signals.append((ANNOTATION_LABEL, "", "", -1, 1, -32768, 32767, "", ann_samples))
    ns = len(hdr_signals)

    head = b"".join([
        _field("0", 8), _field(patient_id, 80), _field(recording_id, 80),
        _field(start_date, 8), _field(start_time, 8), _field(256 + 256 * ns, 8),
        _field("EDF+C" if edf_plus else "", 44), _field(n_records, 8), _field(1, 8), _field(ns, 4),
    ])
    columns = list(zip(*hdr_signals))
    widths = [w for _, w in _SIGNAL_FIELDS]
    for col_idx, width in enumerate(widths[:-1]):
        for v in columns[col_idx]:
            head += _num(v, width) if isinstance(v, (int, float)) and width == 8 else _field(v, width)
    head += b" " * (32 * ns)
    assert len(head) == 256 + 256 * ns

    with open(path, "wb") as fh:
        fh.write(head)
        for r in range(n_records):
            for s in signals:
                fh.write(np.asarray(s.digital[r * s.fs:(r + 1) * s.fs], dtype="<i2").tobytes())
            if edf_plus:
                tal = f"+{r}\x14\x14\x00".encode("latin-1")
                fh.write(tal.ljust(2 * ann_samples, b"\x00"))
