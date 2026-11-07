import numpy as np

from seizelut.eval.operating import choose, gate_mask, kth_of_last, run_events_at, subject_metrics, sweep
from seizelut.models.postprocess import k_of_n


def test_kth_of_last_equals_k_of_n_rule():
    rng = np.random.default_rng(0)
    s = rng.random(500)
    for k in (1, 5, 8, 10):
        for th in (0.3, 0.6, 0.9):
            assert np.array_equal(kth_of_last(s, k) >= th, k_of_n(s >= th, k, 10))


def test_events_are_shifted_to_window_end():
    sk = np.zeros(100)
    sk[10:20] = 1
    assert run_events_at(sk, 0.5) == [(12.0, 22.0)]


def test_gates():
    art = np.array([[1, 0], [1, 1], [0, 0]], bool)
    assert gate_mask(art, "both").tolist() == [False, True, False]
    assert gate_mask(art, "any").tolist() == [True, True, False]


def test_sweep_finds_perfect_detector():
    runs = []
    for i in range(4):
        n = 7200
        score = np.zeros(n)
        score[3000:3060] = 1.0           # seizure at 3000-3060 s
        score[5000] = 0.6                # isolated blip, removed by k-of-10
        runs.append({"subject": f"s{i % 2}", "score": score, "artefact": np.zeros((n, 2), bool),
                     "seizures": np.array([[3001.0, 3061.0]]), "duration_s": float(n + 1)})
    rows = sweep(runs, ks=(1, 8), gates=("none",), thresholds=[0.5, 0.8])
    best = choose(rows)["best_f1"]
    assert best["f1"] == 1.0 and best["fp_per_24h"] == 0.0
    k1 = [r for r in rows if r["k"] == 1 and r["threshold"] == 0.5][0]
    assert k1["precision"] == 0.5        # the blip becomes a false alarm without k-of-10


def test_subject_metrics_zero_precision_rule():
    m = subject_metrics({"a": [1, 1, 1, 24.0], "b": [0, 0, 2, 24.0]})
    assert m["sensitivity"] == 0.5 and m["precision"] == 0.25 and m["fp_per_24h"] == 0.5
