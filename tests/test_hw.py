"""Export -> reference Verilog -> Icarus simulation must agree 100 % with the golden model."""
import shutil

import numpy as np
import pytest

torch = pytest.importorskip("torch")
from seizelut.hw.export import export_dwn, golden_from_export, load_export  # noqa: E402
from seizelut.hw.verilog import generate, make_testbench, simulate, write_vectors  # noqa: E402
from seizelut.models.registry import build  # noqa: E402


@pytest.mark.parametrize("layers,gate", [((48,), "none"), ((40, 20), "both")])
def test_verilog_matches_golden(tmp_path, layers, gate):
    if shutil.which("iverilog") is None:
        pytest.skip("iverilog not installed")
    rng = np.random.default_rng(0)
    X = rng.integers(-300, 300, (3000, 6)).astype(np.int16)
    y = ((X[:, 0] + X[:, 1] > 100) & (X[:, 2] > -50)).astype(int)
    m = build({"type": "dwn", "params": {"bits": 6, "layers": list(layers), "epochs": 8, "batch": 512}}).fit(X, y)
    names = [f"f{i}" for i in range(6)]
    op = {"threshold": 0.5, "gate": gate, "k": 3}
    d = export_dwn(m, names, op, tmp_path / "export", {"run": "unit-test"})
    pkg = load_export(d)
    for f in pkg["thresholds"]["features"]:
        f["width_bits"] = 11
    art = rng.random((len(X), 2)) < 0.3
    g = golden_from_export(pkg, X, art)
    np.testing.assert_array_equal(g["score"], m.score(X).astype(np.int64))      # export == trained model
    info = generate(pkg, tmp_path / "dut.v")
    n = write_vectors(pkg, info, X[:600], art[:600], {k: v[:600] for k, v in g.items() if k != "lut_out"},
                      tmp_path / "vectors.hex")
    make_testbench(pkg, info, tmp_path / "vectors.hex", n, tmp_path / "tb.v")
    ok, out = simulate(tmp_path, tmp_path / "dut.v", tmp_path / "tb.v")
    assert ok, out


def test_test_vectors_match_golden_model(tmp_path, bids_root):
    """Section 8.4: test vectors from raw fixture recordings: features equal the golden feature model,
    scores equal the trained DWN, and the manifest's checksums match the files."""
    import contextlib
    import hashlib
    import json
    import subprocess
    import sys
    from pathlib import Path
    from seizelut.data.bids import discover_runs
    from seizelut.data.edf import read_edf
    from seizelut.data.remote import local_edf
    from seizelut.features import spec as S
    from seizelut.features.golden import extract
    repo = Path(__file__).resolve().parents[1]
    rng = np.random.default_rng(0)
    fcols = [S.FEATURES.index(n) for n in ("eeg_mav_mean", "eeg_ll_max", "eeg_ch1_mav", "present_ecg")]
    X = rng.integers(0, 400, (2000, len(fcols))).astype(np.int16)
    y = (X[:, 0] + X[:, 1] > 400).astype(int)
    m = build({"type": "dwn", "params": {"bits": 4, "layers": [16], "n": 4, "epochs": 2, "batch": 256}}).fit(X, y)
    d = export_dwn(m, [S.FEATURES[c] for c in fcols], {"threshold": 0.5, "gate": "any", "k": 3}, tmp_path / "exp",
                   {"run": "unit-test"})
    keys = ["sub-001_run-01", "sub-002_run-01"]
    r = subprocess.run([sys.executable, "scripts/make_test_vectors.py", "--export", str(d), "--runs", *keys,
                        "--dataset-root", str(bids_root)], cwd=repo, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    man = json.loads((d / "vectors" / "manifest.json").read_text())
    runs = {x.key: x for x in discover_runs(bids_root, ["sub-001", "sub-002"])}
    for key in keys:
        with contextlib.ExitStack() as st:
            sig = {mm: read_edf(st.enter_context(local_edf(runs[key], mm))) for mm in runs[key].modalities}
            ref = extract(sig, int(sig["eeg"].duration_s), "int")["X"].astype(np.int16)
        feats = np.fromfile(d / "vectors" / key / "features.i16", dtype=np.int16).reshape(-1, len(S.FEATURES))
        np.testing.assert_array_equal(feats, ref)
        score = np.fromfile(d / "vectors" / key / "score.i32", dtype=np.int32)
        np.testing.assert_array_equal(score, m.score(ref[:, fcols]).astype(np.int32))
        assert any(k.startswith(f"{key}/inputs/eeg_") for k in man["recordings"][key]["files"])
        for rel, info in man["recordings"][key]["files"].items():
            assert hashlib.sha256((d / "vectors" / rel).read_bytes()).hexdigest() == info["sha256"]
        assert (d / "vectors" / key / "sample.csv").read_text().startswith("second,")
    # Section 8.5: the generated Verilog reproduces the vectors (score, decision, alarm) on every second
    import shutil as _sh
    if _sh.which("iverilog"):
        r = subprocess.run([sys.executable, "scripts/verify_verilog.py", "--export", str(d)], cwd=repo,
                           capture_output=True, text=True)
        assert r.returncode == 0 and "ALL PASS" in r.stdout, r.stdout[-1500:] + r.stderr[-1500:]


def test_baseline_exports_reproduce_the_models(tmp_path):
    """INT8 MLP and TreeLUT packages recompute the trained models' outputs from the JSON alone."""
    from seizelut.hw.export_baselines import export_mlp_int8, export_treelut, mlp_from_export, treelut_from_export
    rng = np.random.default_rng(1)
    X = rng.integers(-200, 200, (1500, 5)).astype(np.int16)
    y = (X[:, 0] - X[:, 2] > 50).astype(int)
    op = {"threshold": 0.1, "gate": "none", "k": 4}
    names = [f"f{i}" for i in range(5)]
    mlp = build({"type": "mlp_int8", "params": {"hidden": [8, 4], "epochs": 3, "batch": 256, "threads": 1}}).fit(X, y)
    d = export_mlp_int8(mlp, names, op, tmp_path / "mlp", {"run": "unit-test"})
    np.testing.assert_allclose(mlp_from_export(d, X), mlp.score(X), rtol=1e-4, atol=1e-4)
    seq = torch.load(d / "mlp_float.pt", weights_only=False)
    assert sum(isinstance(m, torch.nn.Linear) for m in seq) == 3
    tl = build({"type": "treelut", "params": {"n_estimators": 8, "max_depth": 3, "w_tree": 4}}).fit(X, y)
    d2 = export_treelut(tl, names, op, tmp_path / "tl", {"run": "unit-test"})
    np.testing.assert_array_equal(treelut_from_export(d2, X[:300]), tl.score_int(X[:300]))
