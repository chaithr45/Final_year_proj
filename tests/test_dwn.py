"""Check the pure-PyTorch DWN against a literal Python port of torch-dwn's CUDA kernel."""
import numpy as np
import pytest

torch = pytest.importorskip("torch")
from seizelut.models.dwn import (DWN, DistributiveThermometer, EFDFunction, GroupSum, LUTLayer,  # noqa: E402
                                 integer_forward, random_mapping, used_input_bits)


def kernel_reference(x, mapping, luts, alpha, beta, g):
    """Literal port of efd_cuda_kernel.cu (forward and backward)."""
    B, L = x.shape[0], mapping.shape[0]
    n = mapping.shape[1]
    out = np.zeros((B, L))
    xg = np.zeros_like(x)
    lg = np.zeros_like(luts)
    for i in range(B):
        for j in range(L):
            addr = 0
            for lb in range(n):
                addr |= int(x[i, mapping[j, lb]] > 0) << lb
            out[i, j] = luts[j, addr]
            lg[j, addr] += g[i, j]
            for lb in range(n):
                w = 0.0
                a_off = addr & ~(1 << lb)
                for a2 in range(1 << n):
                    dist = bin(a_off ^ (a2 & ~(1 << lb))).count("1")
                    fd = luts[j, a2] * alpha * beta ** dist
                    w += fd if (a2 >> lb) & 1 else -fd
                xg[i, mapping[j, lb]] += w * g[i, j]
    return out, xg, lg


@pytest.mark.parametrize("n", [2, 4, 6])
def test_efd_matches_cuda_kernel(n):
    rng = np.random.default_rng(n)
    B, IN, L = 5, 13, 7
    x = (rng.random((B, IN)) > 0.5).astype(np.float64) * 2 - 1 + rng.normal(0, 0.1, (B, IN))
    mapping = rng.integers(0, IN, (L, n))
    luts = rng.uniform(-1, 1, (L, 1 << n))
    g = rng.normal(0, 1, (B, L))
    alpha, beta = 0.5 * 0.75 ** (n - 1), 0.25 / 0.75
    ref_out, ref_xg, ref_lg = kernel_reference(x, mapping, luts, alpha, beta, g)
    xt = torch.tensor(x, dtype=torch.float64, requires_grad=True)
    lt = torch.tensor(luts, dtype=torch.float64, requires_grad=True)
    out = EFDFunction.apply(xt, torch.tensor(mapping), lt, alpha, beta)
    out.backward(torch.tensor(g))
    np.testing.assert_allclose(out.detach().numpy(), ref_out)
    np.testing.assert_allclose(lt.grad.numpy(), ref_lg, atol=1e-12)
    np.testing.assert_allclose(xt.grad.numpy(), ref_xg, rtol=1e-6, atol=1e-6)


def test_random_mapping_covers_inputs():
    m = random_mapping(10, 6, 5, torch.Generator().manual_seed(0))
    assert m.shape == (5, 6) and set(m.flatten().tolist()) == set(range(10))


def test_groupsum_and_thermometer():
    assert GroupSum(2, 1)(torch.tensor([[1.0, 0, 1, 1]])).tolist() == [[1.0, 2.0]]
    th = DistributiveThermometer(3).fit(np.arange(100).reshape(-1, 1))
    assert th.thresholds.tolist() == [[25, 50, 75]]
    assert th.encode(np.array([[60]])).tolist() == [[1.0, 1.0, 0.0]]


def test_dwn_learns_and_integer_export_matches():
    rng = np.random.default_rng(0)
    X = rng.normal(0, 1, (3000, 4))
    y = ((X[:, 0] + X[:, 1] > 0.5) & (X[:, 2] > -0.5)).astype(int)
    th = DistributiveThermometer(8).fit(X)
    bits = th.encode(X)
    for mapping in ("random", "learnable"):
        model = DWN(bits.shape[1], layers=(64,), n=6, mapping=mapping, tau=1 / 0.3, seed=0)
        opt = torch.optim.Adam(model.parameters(), lr=1e-2)
        yt = torch.tensor(y)
        for _ in range(60):
            loss = torch.nn.functional.cross_entropy(model(bits), yt)
            opt.zero_grad()
            loss.backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            logits = model(bits)
        acc = (logits.argmax(1).numpy() == y).mean()
        assert acc > 0.85, (mapping, acc)
        exp = model.export()
        score = integer_forward(bits.numpy(), exp)
        # GroupSum difference * tau equals the integer popcount difference
        np.testing.assert_allclose(score, ((logits[:, 1] - logits[:, 0]) * model.head.tau).numpy(), atol=1e-4)
        assert used_input_bits(exp, bits.shape[1]).sum() <= bits.shape[1]


def test_lut_layer_learnable_mapping_shapes():
    layer = LUTLayer(20, 8, 6, "learnable")
    out = layer(torch.randint(0, 2, (3, 20)).float())
    assert out.shape == (3, 8) and set(out.unique().tolist()) <= {0.0, 1.0}
    assert layer.input_mapping().shape == (8, 6)


def test_lgn_learns_and_integer_export_matches():
    from seizelut.models.lgn import LGN, lgn_integer_forward
    rng = np.random.default_rng(1)
    X = rng.normal(0, 1, (3000, 4))
    y = ((X[:, 0] > 0) ^ (X[:, 1] > 0.3)).astype(int)
    bits = DistributiveThermometer(8).fit(X).encode(X)
    net = LGN(bits.shape[1], (256, 256), tau=8.0, seed=0)
    opt = torch.optim.Adam(net.parameters(), lr=0.05)
    for _ in range(150):
        loss = torch.nn.functional.cross_entropy(net(bits), torch.tensor(y))
        opt.zero_grad()
        loss.backward()
        opt.step()
    net.eval()
    with torch.no_grad():
        logits = net(bits)
    assert (logits.argmax(1).numpy() == y).mean() > 0.8
    np.testing.assert_allclose(lgn_integer_forward(bits.numpy(), net.export()),
                               ((logits[:, 1] - logits[:, 0]) * net.head.tau).numpy(), atol=1e-3)


def test_treelut_integer_scores_rank_like_xgboost():
    pytest.importorskip("xgboost")
    from seizelut.models.registry import TreeLUTModel
    rng = np.random.default_rng(2)
    X = rng.integers(-200, 200, (4000, 5)).astype(np.int16)
    y = ((X[:, 0] + X[:, 1] > 50) | (X[:, 2] > 150)).astype(int)
    m = TreeLUTModel(w_feature=8, w_tree=4, n_estimators=40, max_depth=3).fit(X, y)
    si, s = m.score_int(X), m.score(X)
    assert si.dtype == np.int64
    # the logit-unit score is a monotone map of the integer sum; thresholds translate exactly
    u = np.unique(s)
    th = float((u[len(u) // 2] + u[len(u) // 2 + 1]) / 2)
    assert np.array_equal(s >= th, si >= m.int_threshold(th))
    from sklearn.metrics import roc_auc_score
    assert roc_auc_score(y, s) > 0.97
    c = m.cost([10] * 5)
    assert c["multipliers"] == 0 and c["trees"] == 40


def test_stateful_dwn_learns_memory_and_export_matches():
    from seizelut.models.stateful import StatefulDWN, batched_integer_forward, stateful_integer_forward
    torch.manual_seed(0)
    rng = np.random.default_rng(3)
    B, T = 256, 40
    x = (rng.random((B, T)) > 0.6).astype(np.float32)
    # label: input on for the last 3 consecutive steps (needs 2 steps of memory)
    y = np.zeros((B, T), np.int64)
    for t in range(2, T):
        y[:, t] = (x[:, t] > 0) & (x[:, t - 1] > 0) & (x[:, t - 2] > 0)
    bits = torch.tensor(np.repeat(x[..., None], 4, axis=2))     # 4 copies of the input bit
    net = StatefulDWN(4, n_state=8, n_vote=64, n=4, mapping="random", tau=3.0, seed=0)
    opt = torch.optim.Adam(net.parameters(), lr=0.02)
    yt = torch.tensor(y)
    for _ in range(150):
        logits, _ = net(bits)
        loss = torch.nn.functional.cross_entropy(logits.reshape(-1, 2), yt.reshape(-1), weight=torch.tensor([1.0, 4.0]))
        opt.zero_grad()
        loss.backward()
        opt.step()
    net.eval()
    with torch.no_grad():
        logits, _ = net(bits)
    pred = logits.argmax(-1).numpy()
    from sklearn.metrics import balanced_accuracy_score
    assert balanced_accuracy_score(y[:, 2:].ravel(), pred[:, 2:].ravel()) > 0.8
    exp = net.export()
    ref = ((logits[..., 1] - logits[..., 0]) * net.head.tau).numpy()
    single, _ = stateful_integer_forward(bits[0].numpy().astype(np.uint8), exp)
    np.testing.assert_allclose(single, ref[0], atol=1e-3)
    batched = batched_integer_forward([bits[i].numpy().astype(np.uint8) for i in range(5)], exp)
    for i in range(5):
        np.testing.assert_allclose(batched[i], ref[i], atol=1e-3)


@pytest.mark.parametrize("cfg", [
    {"type": "lgn", "params": {"bits": 4, "layers": [64, 64], "epochs": 4, "batch": 256, "threads": 1}},
    {"type": "dwn", "params": {"bits": 4, "layers": [32], "epochs": 4, "batch": 256, "threads": 1, "decay_at": 0.5}},
    {"type": "mlp_int8", "params": {"hidden": [16], "epochs": 4, "batch": 256, "threads": 1}},
])
def test_training_resumes_from_epoch_checkpoint(cfg, tmp_path):
    """A fold interrupted after epoch 2 and resumed from its checkpoint gives the uninterrupted model."""
    from seizelut.models.registry import build
    rng = np.random.default_rng(0)
    X = rng.integers(0, 256, size=(1500, 6)).astype(np.int32)
    y = (X[:, 0] + rng.integers(0, 60, 1500) > 200).astype(np.int64)
    ref = build(cfg).fit(X, y).score(X)

    class Stop(Exception):
        pass

    m = build(cfg)
    m.ckpt_path = tmp_path / "fold.pt"
    save = m._ckpt_save

    def save_then_stop(epoch, *a):
        save(epoch, *a)
        if epoch == 2:
            raise Stop
    m._ckpt_save = save_then_stop
    with pytest.raises(Stop):
        m.fit(X, y)
    m2 = build(cfg)
    m2.ckpt_path = tmp_path / "fold.pt"
    assert np.array_equal(m2.fit(X, y).score(X), ref)


def _old_sequences(p, store, subjects, cols, rng):
    """The sampler before the memory fix (every training run held in memory), kept as the reference."""
    T = p["seq_len"]
    seqs, labs, pos_n = [], [], 0
    runs = list(store.iter_runs(subjects))
    for r in runs:
        pos = np.flatnonzero(r.y == 1)
        if len(pos) == 0 or len(r.y) < T:
            continue
        breaks = np.flatnonzero(np.diff(pos) > 1)
        for a, b in zip(np.r_[pos[0], pos[breaks + 1]], np.r_[pos[breaks], pos[-1]]):
            lo, hi = max(0, a - T + p["burn_in"] + 1), min(len(r.y) - T, b - p["burn_in"])
            if hi < lo:
                lo = hi = int(np.clip(a - T // 2, 0, len(r.y) - T))
            for st in rng.integers(lo, hi + 1, p["pos_per_seizure"]):
                seqs.append(r.X[st:st + T][:, cols]); labs.append(r.y[st:st + T]); pos_n += 1
    lens = np.array([max(0, len(r.y) - T) for r in runs], dtype=float)
    for i in rng.choice(len(runs), size=p["neg_ratio"] * pos_n, p=lens / lens.sum()):
        r = runs[i]
        st = int(rng.integers(0, len(r.y) - T))
        seqs.append(r.X[st:st + T][:, cols]); labs.append(r.y[st:st + T])
    return np.stack(seqs), np.stack(labs)


def test_stateful_sequences_and_grouped_scoring_match_reference(tmp_path):
    from seizelut.data.featureset import FeatureStore
    from seizelut.models.registry import StatefulDWNModel
    from seizelut.models.stateful import batched_integer_forward
    rng = np.random.default_rng(5)
    d = tmp_path / "int"
    d.mkdir()
    for s in range(1, 4):
        for run in range(1, 4):
            n = int(rng.integers(30, 400))
            y = np.zeros(n, np.int8)
            for _ in range(int(rng.integers(0, 3))):        # 0-2 seizures, some shorter than the burn-in
                a = int(rng.integers(0, n - 5)); y[a:a + int(rng.integers(3, 40))] = 1
            X = rng.integers(-500, 500, (n, 12)).astype(np.int16)
            X[y == 1, :3] += 400
            np.savez(d / f"sub-{s:03d}_run-{run:02d}.npz", X=X, y=y, artefact=np.zeros((n, 2), bool),
                     present=np.ones((n, 4), bool), seizures=np.zeros((0, 2)), duration_s=float(n))
    store = FeatureStore(root=tmp_path)
    subs, cols = ["sub-001", "sub-002", "sub-003"], [0, 1, 2, 5, 7]
    m = StatefulDWNModel(bits=4, n_state=4, n_vote=16, n=4, mapping="random", seq_len=20, burn_in=4,
                         pos_per_seizure=3, neg_ratio=2, epochs=1, batch=16, threads=1)
    Xn, Yn = m._sequences(store, subs, cols, np.random.default_rng(11))
    Xo, Yo = _old_sequences(m.p, store, subs, cols, np.random.default_rng(11))
    assert Xn.dtype == Xo.dtype and Yn.dtype == Yo.dtype
    np.testing.assert_array_equal(Xn, Xo)
    np.testing.assert_array_equal(Yn, Yo)
    m.fit_store(store, subs, cols, seed=0)
    X_list = [r.X[:, cols] for r in store.iter_runs(subs)]
    ref = batched_integer_forward([m.therm.encode(X).numpy().astype(np.uint8) for X in X_list], m.exported)
    for group in (1, 3, 100):
        for a, b in zip(m.score_runs(X_list, group=group), ref):
            np.testing.assert_array_equal(a, b.astype(np.float32))
