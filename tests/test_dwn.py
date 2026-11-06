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
