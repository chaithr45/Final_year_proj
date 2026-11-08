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
    seq = {"seq_len": 20, "burn_in": 4, "pos_per_seizure": 2, "neg_ratio": 2, "epochs": 1, "batch": 16, "threads": 1}
    cfgs["stateful"] = {"model": {"type": "stateful_dwn", "params": {"bits": 4, "n_state": 4, "n_vote": 16, "n": 4,
                                                                      "mapping": "random", **seq}},
                        "features": {"mi_top": 10}, "train": {"bg_ratio": 3}}
    cfgs["gru"] = {"model": {"type": "gru", "params": {"hidden": 8, **seq}}, "features": {"mi_top": 10},
                   "train": {"bg_ratio": 3}}
    cfgs["logicnet"] = {"model": {"type": "logicnet", "params": {"hidden": [16, 8], "epochs": 1, "batch": 256,
                                                                  "threads": 1}},
                        "features": {"mi_top": 10}, "train": {"bg_ratio": 3}}
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
        assert m["cost_median"].get("total_luts", 1) > 0 and m["cost_median"]
        if name == "gated":
            assert "present_emg" in m["fold_info"][0]["features"]
            assert "teacher lgbm trained" in (rd / "log.txt").read_text()
        if name in ("stateful", "gru"):
            assert len(m["fold_info"][0]["features"]) == 10       # MI selection now applies to sequence models
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


def test_every_m5_variant_runs(tmp_path):
    """Each generated Tier-2 config (scripts/make_m5_configs.py) runs end to end on a synthetic cache."""
    import yaml
    folds = _synthetic_feature_cache(tmp_path / "feat")
    base = {"name": "tiny_base", "seed": 0,
            "model": {"type": "dwn", "params": {"bits": 4, "layers": [20], "n": 4, "mapping": "random",
                                                "epochs": 1, "batch": 256, "threads": 1}},
            "features": {"mi_top": 10}, "train": {"bg_ratio": 3}, "post": {"k": [4], "gate": ["none"], "n_thresholds": 5}}
    (tmp_path / "base.yaml").write_text(yaml.safe_dump(base))
    r = run("scripts/make_m5_configs.py", "--base", tmp_path / "base.yaml", "--out", tmp_path / "m5")
    assert r.returncode == 0, r.stderr
    cfgs = sorted((tmp_path / "m5").glob("*.yaml"))
    assert len(cfgs) == 16
    for c in cfgs:
        d = yaml.safe_load(c.read_text())
        assert d["base_config"] == "tiny_base"
        for t in (d.get("train", {}).get("distill") or {}, d.get("train", {}).get("hard_negative") or {}):
            if "teacher" in t:
                t["teacher"]["params"]["n_estimators"] = 10
        c.write_text(yaml.safe_dump(d, sort_keys=False))
        r = run("scripts/run_inner_cv.py", "--config", c, "--folds-file", folds, "--out", tmp_path / "out",
                "--features-root", tmp_path / "feat")
        assert r.returncode == 0, f"{c.name}: {r.stderr[-1500:]}"
        assert f"RESULT {d['name']}" in r.stdout


def test_run_inner_cv_raw_end_to_end(tmp_path, bids_root):
    """Raw-EEG CNN and TCN on two folds of the fixture: train from a segment cache, stream the held-out
    recordings, score, and write one finished run per model."""
    import numpy as np
    import yaml
    from seizelut.data.bids import discover_runs
    from seizelut.data.split import official_train_subjects
    runs = discover_runs(bids_root, official_train_subjects())
    assert {r.subject for r in runs} == {"sub-001", "sub-002"}
    rng = np.random.default_rng(0)
    n = 300
    data = tmp_path / "chrono"
    data.mkdir()
    keys = np.zeros((n, 4))
    keys[:, 0] = rng.integers(0, len(runs), n)
    keys[:, 3] = rng.random(n) < 0.3
    x = rng.normal(0, 20, size=(n, 500, 2)).astype(np.float32)
    x[keys[:, 3] == 1] *= 3
    np.save(data / "train_x.npy", x)
    np.save(data / "train_y.npy", keys[:, 3].astype(np.uint8))
    np.save(data / "train_keys.npy", keys)
    (tmp_path / "cc.yaml").write_text(yaml.safe_dump({"train_subjects": "official_train"}))
    feat = tmp_path / "feat" / "int"
    feat.mkdir(parents=True)
    for r in runs:
        m = 4000
        y = np.zeros(m, np.int8)
        y[1000:1060] = 1
        np.savez(feat / f"{r.key}.npz", X=np.zeros((m, 117), np.int16), y=y, artefact=np.zeros((m, 2), bool),
                 present=np.ones((m, 4), bool), seizures=np.array([[1000.0, 1061.0]]), duration_s=float(m + 1))
    (tmp_path / "folds.json").write_text(json.dumps({"folds": {"sub-001": 0, "sub-002": 1}}))
    cfg = {"name": "raw_test", "seed": 0, "data": {"cache_dir": str(data), "config": str(tmp_path / "cc.yaml")},
           "models": [{"name": "cnn_t", "type": "cnn1d", "params": {"channels": [4, 8, 8, 8]}},
                      {"name": "tcn_t", "type": "tcn", "params": {"channels": 4, "dilations": [1, 2]}}],
           "train": {"epochs": 1, "batch": 64}, "post": {"k": [4], "gate": ["none"], "n_thresholds": 5}}
    (tmp_path / "raw.yaml").write_text(yaml.safe_dump(cfg))
    r = run("scripts/run_inner_cv_raw.py", "--config", tmp_path / "raw.yaml", "--device", "cpu",
            "--folds-file", tmp_path / "folds.json", "--dataset-root", bids_root, "--features-root", tmp_path / "feat",
            "--out", tmp_path / "out")
    assert r.returncode == 0, r.stderr[-2000:]
    for name in ("cnn_t", "tcn_t"):
        assert f"RESULT {name}" in r.stdout
        d = next((tmp_path / "out" / "results" / "runs").glob(f"*_{name}_s0"))
        m = json.loads((d / "metrics.json").read_text())
        assert m["cost_median"]["multipliers"] > 0 and not (d / ".gitignore").exists()
    # a second call finds both runs finished and starts nothing
    r2 = run("scripts/run_inner_cv_raw.py", "--config", tmp_path / "raw.yaml", "--device", "cpu",
             "--folds-file", tmp_path / "folds.json", "--dataset-root", bids_root, "--features-root", tmp_path / "feat",
             "--out", tmp_path / "out")
    assert r2.returncode == 0, r2.stderr[-2000:]
    assert "cnn_t: a finished run exists, skipped" in r2.stdout
    assert len(list((tmp_path / "out" / "results" / "runs").glob("*_cnn_t_s0"))) == 1
