import numpy as np
import pytest

from seizelut.data.edf import EdfSignal, parse_header, read_edf, read_header, record_onsets, write_edf


def _write(tmp_path, n_sec=7):
    rng = np.random.default_rng(0)
    a = rng.integers(-32768, 32767, n_sec * 256, dtype=np.int16)
    b = rng.integers(-32768, 32767, n_sec * 25, dtype=np.int16)
    p = tmp_path / "x.edf"
    write_edf(p, [EdfSignal("BTEleft SD", a, 256, -1311.0, 1306.0),
                  EdfSignal("EEG SD ACC X", b, 25, -1.0, 1.0, "g")])
    return p, a, b


def test_roundtrip_is_bit_exact(tmp_path):
    p, a, b = _write(tmp_path)
    d = read_edf(p)
    assert d.labels == ["BTEleft SD", "EEG SD ACC X"]
    assert d.fs == {"BTEleft SD": 256.0, "EEG SD ACC X": 25.0}
    assert np.array_equal(d.digital["BTEleft SD"], a)
    assert np.array_equal(d.digital["EEG SD ACC X"], b)
    assert d.duration_s == 7 and not d.warnings
    assert d.header.is_edf_plus and not d.header.is_discontinuous


def test_physical_conversion_hits_header_limits(tmp_path):
    p = tmp_path / "lim.edf"
    write_edf(p, [EdfSignal("c", np.array([-32768, 32767] * 128, dtype=np.int16), 256, -1311.0, 1306.0)])
    phys = read_edf(p).physical("c")
    assert phys.min() == pytest.approx(-1311.0) and phys.max() == pytest.approx(1306.0)


def test_header_parses_from_bytes_alone(tmp_path):
    p, _, _ = _write(tmp_path)
    raw = p.read_bytes()[:4096]
    h = parse_header(raw)
    assert h == read_header(p)
    assert h.sampling_rate("EEG SD ACC X") == 25.0 and h.n_records == 7


def test_record_onsets_contiguous(tmp_path):
    p, _, _ = _write(tmp_path)
    assert np.array_equal(record_onsets(p), np.arange(7.0))


def test_truncated_file_reports_warning(tmp_path):
    p, a, _ = _write(tmp_path)
    data = p.read_bytes()
    p.write_bytes(data[:-100])
    d = read_edf(p)
    assert d.n_records_read == 6 and d.warnings
    assert np.array_equal(d.digital["BTEleft SD"], a[: 6 * 256])


def test_matches_pyedflib(bids_root):
    pyedflib = pytest.importorskip("pyedflib")
    for p in sorted(bids_root.glob("sub-*/ses-01/*/*.edf")):
        d = read_edf(p)
        with pyedflib.EdfReader(str(p)) as f:
            labels = [lb for lb in f.getSignalLabels() if lb != "EDF Annotations"]
            assert labels == d.labels
            for i, lb in enumerate(labels):
                assert np.array_equal(f.readSignal(i, digital=True), d.digital[lb]), (p.name, lb)
                np.testing.assert_allclose(f.readSignal(i), d.physical(lb), atol=1e-9)
                assert f.getSampleFrequency(i) == d.fs[lb]
