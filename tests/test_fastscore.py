import numpy as np
import pytest

from seizelut.eval.events import mask_to_events
from seizelut.eval.fastscore import prepare_ref, score_events
from seizelut.eval.szcore import score_recording

pytest.importorskip("timescoring")


def test_fastscore_equals_timescoring():
    rng = np.random.default_rng(7)
    for _ in range(300):
        n = int(rng.integers(600, 5000))
        ref = np.zeros(n, bool)
        for _ in range(rng.integers(0, 4)):
            a = int(rng.integers(0, n - 50))
            ref[a:a + int(rng.integers(3, 500))] = True
        hyp = np.zeros(n, bool)
        for _ in range(rng.integers(0, 8)):
            a = int(rng.integers(0, n - 20))
            hyp[a:a + int(rng.integers(1, 400))] = True
        R, H = mask_to_events(ref), mask_to_events(hyp)
        ts = score_recording("s", "r", R, H, n)
        tp, fp, nref = score_events(prepare_ref(R, n), H)
        assert (tp, fp, nref) == (ts.tp, ts.fp, ts.ref_events), (R, H)
