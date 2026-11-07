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
