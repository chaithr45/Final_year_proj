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
