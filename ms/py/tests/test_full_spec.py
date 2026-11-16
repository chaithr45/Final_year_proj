"""Full-data limits and the step-down rule (ms/py/full_spec.py, LOG L20)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import full_spec  # noqa: E402

LV = [0.25, 0.5, 1, 2, 4, 8, 16]


def fam(status, limit):
    lv = [{"name": f"eeg_white_{x:g}uVrms", "level": x, "unit": "uVrms"} for x in LV]
    return {"status": status, "limit": limit, "levels": lv, "limit_unit": "uVrms"}


def v(ok):
    return {"tolerated": ok, "d_f1": 0.0, "d_fp24": 0.0, "wilcoxon_p": 0.5, "marginal": False}


def n(x):
    return f"eeg_white_{x:g}uVrms"


def test_confirmed_and_note():
    r = full_spec.resolve(fam("limit", 8), {n(8): v(True), n(16): v(False)})
    assert (r["status"], r["limit"], r["pending"], r["note"]) == ("limit", 8, None, None)
    r = full_spec.resolve(fam("limit", 8), {n(8): v(True), n(16): v(True)})
    assert r["limit"] == 8 and "kept at the subset limit" in r["note"]


def test_step_down():
    r = full_spec.resolve(fam("limit", 8), {n(8): v(False), n(16): v(False)})
    assert (r["status"], r["pending"]) == ("pending", n(4))
    r = full_spec.resolve(fam("limit", 8), {n(8): v(False), n(4): v(False), n(2): v(True)})
    assert (r["status"], r["limit"]) == ("limit", 2) and "2 grid step" in r["note"]
    r = full_spec.resolve(fam("limit", 1), {n(1): v(False), n(0.5): v(False), n(0.25): v(False)})
    assert (r["status"], r["limit"]) == ("none tolerated", None)


def test_beyond_grid_and_none():
    r = full_spec.resolve(fam("beyond grid", 16), {n(16): v(True)})
    assert (r["status"], r["limit"]) == ("beyond grid", 16)
    r = full_spec.resolve(fam("beyond grid", 16), {n(16): v(False), n(8): v(True)})
    assert (r["status"], r["limit"]) == ("limit", 8)
    r = full_spec.resolve(fam("none tolerated", None), {n(0.25): v(True)})
    assert r["status"] == "none tolerated"
    r = full_spec.resolve(fam("limit", 8), {})
    assert (r["status"], r["pending"]) == ("pending", n(8))


def test_load_full_results(tmp_path):
    job = {"name": n(8), "seed": 0, "tolerated": True, "d_f1": -0.001, "d_fp24": 0.0, "wilcoxon_p": 0.4,
           "marginal": False}
    (tmp_path / "confirm_limits.json").write_text(json.dumps({"jobs": [job]}))
    (tmp_path / "confirm_limits_runs3.json").write_text(json.dumps({"jobs": [{**job, "tolerated": False}]}))
    assert full_spec.load_full_results(tmp_path)[n(8)]["tolerated"] is True     # quick runs are ignored
    (tmp_path / "confirm_stepdown_x.json").write_text(json.dumps({"jobs": [{**job, "tolerated": False}]}))
    try:
        full_spec.load_full_results(tmp_path)
        raise AssertionError("conflicting verdicts must stop the build")
    except SystemExit:
        pass
