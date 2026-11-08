"""Run the M1 scripts end to end on the synthetic fixture (what CI can do without real data)."""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def run(*args):
    return subprocess.run([sys.executable, *map(str, args)], cwd=REPO, capture_output=True, text=True)


def test_verify_data_on_fixture(bids_root):
    r = run("scripts/verify_data.py", "--root", bids_root, "--expected", bids_root.parent / "expected_counts.json")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "VERIFIED" in r.stdout


def test_verify_data_detects_missing_file(bids_root, tmp_path):
    import shutil
    copy = tmp_path / "bids"
    shutil.copytree(bids_root, copy)
    next(copy.glob("sub-002/ses-01/emg/*.edf")).unlink()
    r = run("scripts/verify_data.py", "--root", copy, "--expected", bids_root.parent / "expected_counts.json")
    assert r.returncode == 1 and "sidecar without EDF" in r.stdout


def test_signal_audit_and_report_on_fixture(bids_root, tmp_path):
    stats = tmp_path / "signal_stats.jsonl"
    r = run("scripts/audit_signals.py", "--root", bids_root, "--out", stats, "--workers", "1")
    assert r.returncode == 0, r.stdout + r.stderr
    recs = [json.loads(line) for line in stats.read_text().splitlines()]
    assert len(recs) == 13 and not any("error" in x for x in recs)
    eeg = next(x for x in recs if x["file"].endswith("sub-001_ses-01_task-szMonitoring_run-01_eeg.edf"))
    assert eeg["channels"]["BTEleft SD"]["flat_spans"] == 1 and eeg["record_gaps"] == 0

    report = tmp_path / "audit.md"
    r = run("scripts/audit_data.py", "--root", bids_root, "--signal-stats", stats, "--report", report,
            "--tables", tmp_path / "tables", "--figures", tmp_path / "figs", "--listing", tmp_path / "none.json")
    assert r.returncode == 0, r.stdout + r.stderr
    text = report.read_text()
    assert "Contradictions with Section 3" in text and "| left | BTEleft SD + CROSStop SD | 2 |" in text
    summary = json.loads(report.with_suffix(".json").read_text())
    assert summary["n_seizures"] == 4 and summary["n_subjects"] == 3
    assert (tmp_path / "figs" / "seizure_duration_hist.png").exists()


def test_evaluate_predictions_end_to_end(tmp_path):
    """The laptop scores ChronoNet with this script unattended: it must run on 1 Hz predictions."""
    import numpy as np
    pred, rd = tmp_path / "pred", tmp_path / "run"
    pred.mkdir()
    rd.mkdir()
    (rd / ".gitignore").write_text("*\n")
    rng = np.random.default_rng(0)
    for i, sz in enumerate([(100, 160), (300, 340), None]):
        y = np.zeros(600, np.int8)
        if sz:
            y[sz[0]:sz[1]] = 1
        p = np.clip(0.6 * y + 0.5 * rng.random(600), 0, 1).astype(np.float32)
        rms = np.full(600, 40.0, np.float32)
        np.savez_compressed(pred / f"sub-00{i + 1}_run-01.npz", y_pred=p, y_true=y, rms1=rms, rms2=rms,
                            duration_s=600.0)
    r = run("scripts/baselines/evaluate_predictions.py", "--run", rd, "--predictions", pred)
    assert r.returncode == 0, r.stderr
    m = json.loads((rd / "metrics.json").read_text())
    assert m["n_recordings"] == 3 and m["seizeit2_as_published"]["n_rec_auc"] == 2
    assert 0 < m["seizeit2_as_published"]["aupr_rec_mean"] <= 1
    assert "Per recording" in (rd / "metrics.md").read_text()
    assert not (rd / ".gitignore").exists()


def _synthetic_feature_cache(root, n_sub=6, n_win=900):
    """117-feature integer cache: one run per patient, one seizure each, EEG/ECG features informative."""
    import numpy as np
    from seizelut.features import spec as S
    d = root / "int"
    d.mkdir(parents=True)
    rng = np.random.default_rng(0)
    eeg = [i for i, n in enumerate(S.FEATURES) if n.startswith("eeg_")][:6]
    ecg = [i for i, n in enumerate(S.FEATURES) if n.startswith("ecg_log")][:2]
    for s in range(1, n_sub + 1):
        X = rng.integers(0, 200, size=(n_win, len(S.FEATURES))).astype(np.int16)
        y = np.zeros(n_win, np.int8)
        a = 200 + 50 * s
        y[a:a + 60] = 1
        X[a:a + 60][:, eeg + ecg] += 150
        X[:, [S.FEATURES.index(n) for n in S.FEATURES if n.startswith("present_")]] = 1
        np.savez(d / f"sub-{s:03d}_run-01.npz", X=X, y=y, artefact=np.zeros((n_win, 2), bool),
                 present=np.ones((n_win, 4), bool), seizures=np.array([[a, a + 61.0]]), duration_s=float(n_win + 1))
    folds = {"folds": {f"sub-{s:03d}": (s - 1) % 2 for s in range(1, n_sub + 1)}}
    (root / "folds.json").write_text(json.dumps(folds))
    return root / "folds.json"


def test_run_inner_cv_end_to_end_with_tier2_switches(tmp_path):
    """The cloud queue runs this script unattended: the default DWN path and every Tier-2 switch must run."""
    import yaml
    folds = _synthetic_feature_cache(tmp_path / "feat")
    dwn = {"bits": 4, "layers": [16], "n": 4, "mapping": "random", "epochs": 1, "batch": 256, "threads": 1}
    post = {"k": [4], "gate": ["none"], "n_thresholds": 5}
    cfgs = {
        "base": {"model": {"type": "dwn", "params": dwn}, "features": {"mi_top": 10}, "train": {"bg_ratio": 3}},
        "gated": {"model": {"type": "dwn", "params": dwn},
                  "features": {"mi_top": 10, "always": ["present_ecg", "present_emg", "ecg_quality_bad"]},
                  "train": {"bg_ratio": 3, "modality_dropout": 0.2,
                            "distill": {"teacher": {"type": "lgbm", "params": {"n_estimators": 10, "n_jobs": 1}}},
                            "hard_negative": {"by": "teacher", "top_fraction": 0.01,
                                              "teacher": {"type": "lgbm", "params": {"n_estimators": 10}}}}},
        "late": {"model": {"type": "dwn_late", "params": {**dwn, "groups": {
                     "eeg": {"prefix": ["eeg_"], "mi_top": 8, "layers": [12]},
                     "ecg": {"prefix": ["ecg_", "present_ecg"], "layers": [4]}}}},
                 "features": "all", "train": {"bg_ratio": 3}},
    }
    cfgs["gated"]["model"] = {"type": "dwn", "params": {**dwn, "distill_alpha": 0.5}}
    for name, c in cfgs.items():
        cfg = {"name": f"t_{name}", "seed": 0, **c, "post": post}
        path = tmp_path / f"{name}.yaml"
        path.write_text(yaml.safe_dump(cfg, sort_keys=False))
        r = run("scripts/run_inner_cv.py", "--config", path, "--folds-file", folds, "--out", tmp_path / "out",
                "--features-root", tmp_path / "feat")
        assert r.returncode == 0, f"{name}: {r.stderr[-2000:]}"
        assert f"RESULT t_{name}" in r.stdout
        rd = next((tmp_path / "out" / "results" / "runs").glob(f"*_t_{name}_s0"))
        m = json.loads((rd / "metrics.json").read_text())
        assert m["cost_median"]["total_luts"] > 0
        if name == "gated":
            assert "present_emg" in m["fold_info"][0]["features"]
            assert "teacher lgbm trained" in (rd / "log.txt").read_text()
        if name == "late":
            assert "late fusion: ecg" in (rd / "log.txt").read_text()
            assert m["cost_median"]["fusion_adder_luts"] > 0
    assert not list(Path(REPO / "results" / "runs").glob("*_t_base_s0"))
    base = next((tmp_path / "out" / "results" / "runs").glob("*_t_base_s0"))
    r = run("scripts/m5_breakdown.py", "--run", base, "--missing", "--out", tmp_path / "out",
            "--features-root", tmp_path / "feat", "--folds-file", folds)
    assert r.returncode == 0, r.stderr[-2000:]
    b = json.loads((base / "breakdown.json").read_text())
    assert sum(v["seizures"] for v in b["by_class"].values()) == 6
    assert set(b["missing_modality"]) == {"intact", "no_ecg", "no_emg", "no_mov", "eeg_only"}
