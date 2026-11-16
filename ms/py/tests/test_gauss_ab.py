"""Generator A/B: criterion and level rule (ms/py/gauss_ab.py, grids.gauss_ab_level)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gauss_ab  # noqa: E402


def _rows(f_sum, f_exact, fa_sum, fa_exact):
    R = []
    for s, (a, b, c, d) in enumerate(zip(f_sum, f_exact, fa_sum, fa_exact)):
        R.append({"name": "eeg_white_2uVrms", "seed": s, "f1": a, "fp_per_24h": c})
        R.append({"name": "eeg_white_2uVrms_refgauss", "seed": s, "f1": b, "fp_per_24h": d})
    return R


def test_same_and_different():
    clean = {"f1": 0.34, "fp_per_24h": 0.76}
    r = gauss_ab.compare(clean, _rows([0.33] * 5, [0.32] * 5, [0.8] * 5, [0.85] * 5), 0.03, 0.12)
    assert r["same"] and r["same_verdict"]
    assert abs(r["diff_f1"] - 0.01) < 1e-12 and abs(r["diff_fp24"] + 0.05) < 1e-12
    r = gauss_ab.compare(clean, _rows([0.33] * 5, [0.28] * 5, [0.8] * 5, [0.8] * 5), 0.03, 0.12)
    assert not r["same"] and not r["same_verdict"]          # exact Gaussian drops F1 by 0.06 -> not tolerated
    r = gauss_ab.compare(clean, _rows([0.33] * 5, [0.33] * 5, [0.8] * 5, [1.0] * 5), 0.03, 0.12)
    assert not r["same"]                                     # false-alarm difference 0.2 > 0.12


def test_level_rule(tmp_path, monkeypatch):
    import json
    import grids
    fake = tmp_path / "ms/results/phase1"
    fake.mkdir(parents=True)
    lv = [{"level": x} for x in (0.25, 0.5, 1, 2, 4, 8, 16)]
    monkeypatch.setattr(grids, "__file__", str(tmp_path / "ms/py/grids.py"))
    for status, limit, want in (("limit", 2, 2), ("beyond grid", 16, 16), ("none tolerated", None, 0.25)):
        (fake / "tolerance.json").write_text(json.dumps(
            {"grids": {"eeg": {"families": {"eeg/white": {"status": status, "limit": limit, "levels": lv}}}}}))
        assert grids.gauss_ab_level() == want
        jobs = grids.get("gauss_ab", [0])
        assert len(jobs) == 10 and sum(j["impair"]["eeg"].get("reference_gaussian", False) for j in jobs) == 5
