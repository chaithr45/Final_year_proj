"""Model zoo for the Tier-1 comparison (Section 6.2), one interface for all families.

    m = build(cfg["model"]); m.fit(X, y); s = m.score(X)   # higher = more seizure-like
    m.cost(feature_bits) -> estimated hardware cost (src/hw/cost.py)

Every family sees the same cached integer features, folds and post-processing.
"""
from __future__ import annotations

import math
import time

import numpy as np

from ..hw import cost as hw


class Model:
    name = "base"
    ckpt_path = None        # set by the CV runner: per-epoch training state so a fold survives restarts

    def _ckpt_load(self, mods, opt, sched, gen):
        """Restore the state saved after the last finished epoch; returns the epoch to start from."""
        from pathlib import Path
        if not self.ckpt_path or not Path(self.ckpt_path).exists():
            return 0
        import torch
        st = torch.load(self.ckpt_path, map_location="cpu", weights_only=False)
        for k, m in mods.items():
            m.load_state_dict(st["mods"][k])
        opt.load_state_dict(st["opt"])
        if sched is not None:
            sched.load_state_dict(st["sched"])
        gen.set_state(st["gen"])
        torch.set_rng_state(st["rng"])
        getattr(self, "log", lambda *a: None)(f"    resumed after epoch {st['epoch']} (fold checkpoint)")
        return st["epoch"]

    def _ckpt_save(self, epoch, mods, opt, sched, gen):
        if not self.ckpt_path:
            return
        import os
        import torch
        tmp = str(self.ckpt_path) + ".tmp"
        torch.save({"epoch": epoch, "mods": {k: m.state_dict() for k, m in mods.items()}, "opt": opt.state_dict(),
                    "sched": sched.state_dict() if sched is not None else None, "gen": gen.get_state(),
                    "rng": torch.get_rng_state()}, tmp)
        os.replace(tmp, self.ckpt_path)         # atomic: never a half-written checkpoint

    def fit(self, X, y):
        raise NotImplementedError

    def score(self, X) -> np.ndarray:
        raise NotImplementedError

    def cost(self, feature_bits) -> dict:
        return {}


class LogReg(Model):
    name = "lr"

    def __init__(self, C=1.0, class_weight="balanced", max_iter=2000):
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        self.m = make_pipeline(StandardScaler(), LogisticRegression(C=C, class_weight=class_weight, max_iter=max_iter))

    def fit(self, X, y):
        self.m.fit(X.astype(np.float32), y)
        self.n_in = X.shape[1]
        return self

    def score(self, X):
        return self.m.decision_function(X.astype(np.float32))

    def cost(self, feature_bits):
        return hw.linear_cost(self.n_in)


class _Trees(Model):
    def _tree_stats(self):
        raise NotImplementedError

    def cost(self, feature_bits):
        nodes, distinct, leaves, trees = self._tree_stats()
        return hw.tree_cost(nodes, distinct, leaves, trees, feature_bits=int(np.max(feature_bits)))


class LightGBM(_Trees):
    name = "lgbm"

    def __init__(self, **params):
        import lightgbm as lgb
        p = dict(n_estimators=300, num_leaves=31, learning_rate=0.05, subsample=0.8, subsample_freq=1,
                 colsample_bytree=0.8, min_child_samples=50, verbose=-1, n_jobs=4)
        p.update(params)
        self.m = lgb.LGBMClassifier(**p)

    def fit(self, X, y):
        self.m.fit(X, y)
        return self

    def score(self, X):
        return self.m.predict_proba(X)[:, 1]

    def _tree_stats(self):
        df = self.m.booster_.trees_to_dataframe()
        splits = df[df["split_feature"].notna()]
        distinct = len(set(zip(splits["split_feature"], splits["threshold"])))
        return len(splits), distinct, int(df["split_feature"].isna().sum()), df["tree_index"].nunique()


class XGBoost(_Trees):
    name = "xgb"

    def __init__(self, **params):
        import xgboost as xgb
        p = dict(n_estimators=300, max_depth=6, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                 tree_method="hist", n_jobs=4, eval_metric="logloss")
        p.update(params)
        self.m = xgb.XGBClassifier(**p)

    def fit(self, X, y):
        self.m.fit(X, y)
        return self

    def score(self, X):
        return self.m.predict_proba(X)[:, 1]

    def _tree_stats(self):
        df = self.m.get_booster().trees_to_dataframe()
        splits = df[df["Feature"] != "Leaf"]
        distinct = len(set(zip(splits["Feature"], splits["Split"])))
        return len(splits), distinct, int((df["Feature"] == "Leaf").sum()), df["Tree"].nunique()


class CatBoost(_Trees):
    name = "catboost"

    def __init__(self, **params):
        from catboost import CatBoostClassifier
        p = dict(iterations=300, depth=6, learning_rate=0.1, verbose=False, thread_count=4, random_seed=0)
        p.update(params)
        self.m = CatBoostClassifier(**p)

    def fit(self, X, y):
        self.m.fit(X, y)
        return self

    def score(self, X):
        return self.m.predict_proba(X)[:, 1]

    def _tree_stats(self):
        n_trees = self.m.tree_count_
        depth = self.m.get_params().get("depth", 6)
        borders = sum(len(b) for b in self.m.get_borders().values()) if hasattr(self.m, "get_borders") else n_trees * depth
        return n_trees * depth, borders, n_trees * (1 << depth), n_trees


class RandomForest(_Trees):
    name = "rf"

    def __init__(self, **params):
        from sklearn.ensemble import RandomForestClassifier
        p = dict(n_estimators=200, max_depth=12, min_samples_leaf=20, n_jobs=4, class_weight="balanced_subsample",
                 random_state=0)
        p.update(params)
        self.m = RandomForestClassifier(**p)

    def fit(self, X, y):
        self.m.fit(X, y)
        return self

    def score(self, X):
        return self.m.predict_proba(X)[:, 1]

    def _tree_stats(self):
        nodes, distinct, leaves = 0, set(), 0
        for est in self.m.estimators_:
            t = est.tree_
            inner = t.children_left >= 0
            nodes += int(inner.sum())
            leaves += int((~inner).sum())
            distinct |= set(zip(t.feature[inner].tolist(), np.round(t.threshold[inner], 3).tolist()))
        return nodes, len(distinct), leaves, len(self.m.estimators_)


class DWNModel(Model):
    """Thermometer + DWN (src/models/dwn.py). score() is the INTEGER popcount difference of the
    exported network (hardware-exact).

    Tier-2 switches (Section 6.3), all off by default:
      encoder: distributive | uniform | gaussian | learned (N2; learned uses comparator_penalty)
      loss: ce | focal | gce | sce (N5 noise-robust); onset_weight (N5, first 20 s of seizures)
      mil_topk: fraction of each seizure's windows that must score high (N5 multiple-instance)
      distill_alpha: weight of the teacher's soft targets (N4; soft targets passed to fit)
    """
    name = "dwn"

    def __init__(self, bits=8, layers=(200,), n=6, mapping="learnable", tau=1 / 0.3, epochs=30, lr=1e-2,
                 batch=2048, decay_at=0.7, loss="ce", focal_gamma=2.0, gce_q=0.7, sce_ab=(0.1, 1.0),
                 encoder="distributive", comparator_penalty=1e-4, onset_weight=1.0, mil_topk=None,
                 distill_alpha=0.0, distill_T=2.0, seed=0, device="cpu", threads=4, log=None):
        self.p = dict(bits=bits, layers=tuple(layers), n=n, mapping=mapping, tau=tau, epochs=epochs, lr=lr,
                      batch=batch, decay_at=decay_at, loss=loss, focal_gamma=focal_gamma, gce_q=gce_q,
                      sce_ab=tuple(sce_ab), encoder=encoder, comparator_penalty=comparator_penalty,
                      onset_weight=onset_weight, mil_topk=mil_topk, distill_alpha=distill_alpha,
                      distill_T=distill_T, seed=seed, device=device)
        self.threads = threads
        self.log = log or (lambda *a: None)

    def _loss(self, out, yb, w, sw):
        import torch
        import torch.nn.functional as F
        p = self.p
        logp = F.log_softmax(out, 1)
        lp_y = logp.gather(1, yb[:, None]).squeeze(1)
        if p["loss"] == "focal":
            per = -(1 - lp_y.exp()) ** p["focal_gamma"] * lp_y
        elif p["loss"] == "gce":
            per = (1 - lp_y.exp() ** p["gce_q"]) / p["gce_q"]
        elif p["loss"] == "sce":
            a, b = p["sce_ab"]
            onehot = F.one_hot(yb, 2).float().clamp_min(1e-4)
            rce = -(logp.exp() * onehot.log()).sum(1)
            per = -a * lp_y + b * rce
        else:
            per = -lp_y
        return (per * w[yb] * sw).sum() / (w[yb] * sw).sum()

    def fit(self, X, y, onset=None, bags=None, soft=None):
        import torch
        import torch.nn.functional as F
        from .dwn import DWN, DistributiveThermometer
        from .encoders import LearnedThermometer, make_encoder
        torch.set_num_threads(self.threads)
        p = self.p
        torch.manual_seed(p["seed"])
        dev = torch.device(p["device"])
        learned = p["encoder"] == "learned"
        base = make_encoder("distributive" if learned else p["encoder"], p["bits"]).fit(X)
        if learned:
            q75, q25 = np.percentile(X, [75, 25], axis=0)
            self.lenc = LearnedThermometer(base, (q75 - q25) / 8.0).to(dev)
            xin = torch.as_tensor(X.astype(np.float32))
            n_bits = base.n_bits
        else:
            self.therm = base
            xin = self.therm.encode(X)
            n_bits = xin.shape[1]
        self.net = DWN(n_bits, p["layers"], p["n"], p["mapping"], p["tau"], p["seed"]).to(dev)
        params = list(self.net.parameters()) + (list(self.lenc.parameters()) if learned else [])
        opt = torch.optim.Adam(params, lr=p["lr"])
        sched = torch.optim.lr_scheduler.StepLR(opt, step_size=max(1, int(p["epochs"] * p["decay_at"])), gamma=0.1)
        yt = torch.as_tensor(y, dtype=torch.long)
        w = torch.tensor([1.0, float((y == 0).sum()) / max(1, int((y == 1).sum()))], device=dev)
        sw_all = torch.ones(len(y))
        if onset is not None and p["onset_weight"] != 1.0:
            sw_all[torch.as_tensor(onset, dtype=torch.bool)] = float(p["onset_weight"])
        soft_t = torch.as_tensor(soft, dtype=torch.float32) if soft is not None else None
        bag_t = torch.as_tensor(bags, dtype=torch.long) if bags is not None else None
        g = torch.Generator().manual_seed(p["seed"])
        mods = {"net": self.net, **({"lenc": self.lenc} if learned else {})}
        start = self._ckpt_load(mods, opt, sched, g)
        for ep in range(start, p["epochs"]):
            self.net.train()
            perm = torch.randperm(len(yt), generator=g)
            tot, t0 = 0.0, time.time()
            for i in range(0, len(perm), p["batch"]):
                idx = perm[i:i + p["batch"]]
                xb = self.lenc(xin[idx].to(dev)) if learned else xin[idx].to(dev)
                yb = yt[idx].to(dev)
                out = self.net(xb)
                sw = sw_all[idx].to(dev)
                if p["mil_topk"] and bag_t is not None:
                    # N5 MIL: positives of a seizure only need their top-k fraction to score high
                    bb = bag_t[idx]
                    keep = torch.ones(len(idx), dtype=torch.bool)
                    margin = (out[:, 1] - out[:, 0]).detach()
                    for b in torch.unique(bb[bb >= 0]):
                        m = torch.nonzero(bb == b).squeeze(1)
                        k = max(1, int(np.ceil(p["mil_topk"] * len(m))))
                        drop = m[torch.argsort(margin[m], descending=True)[k:]]
                        keep[drop] = False
                    sw = sw * keep.float().to(dev)
                loss = self._loss(out, yb, w, sw)
                if p["distill_alpha"] > 0 and soft_t is not None:
                    T = p["distill_T"]
                    st = soft_t[idx].to(dev).clamp(1e-4, 1 - 1e-4)
                    q = torch.stack([1 - st, st], 1)
                    loss = (1 - p["distill_alpha"]) * loss + p["distill_alpha"] * T * T * F.kl_div(
                        F.log_softmax(out / T, 1), q, reduction="batchmean")
                if learned:
                    loss = loss + p["comparator_penalty"] * self.lenc.penalty()
                opt.zero_grad()
                loss.backward()
                opt.step()
                tot += float(loss.detach()) * len(idx)
            sched.step()
            self.log(f"    epoch {ep + 1}/{p['epochs']} loss {tot / len(perm):.4f} ({time.time() - t0:.0f} s)")
            self._ckpt_save(ep + 1, mods, opt, sched, g)
        self.net.eval()
        if learned:
            self.therm = self.lenc.freeze()
            self.lenc = None
        self.exported = self.net.export()
        return self

    def score(self, X):
        from .dwn import integer_forward
        out = []
        for i in range(0, len(X), 200_000):
            out.append(integer_forward(self.therm.encode(X[i:i + 200_000]).numpy().astype(np.uint8), self.exported))
        return np.concatenate(out).astype(np.float32)

    def cost(self, feature_bits):
        from .dwn import used_input_bits
        used = used_input_bits(self.exported, self.therm.n_bits)
        finite = np.isfinite(self.therm.thresholds).ravel()
        c = hw.dwn_cost(self.exported, self._finite_therm(), list(feature_bits), used & finite)
        return c

    def _finite_therm(self):
        from .dwn import DistributiveThermometer
        t = DistributiveThermometer(self.therm.num_bits)
        th = self.therm.thresholds.astype(np.float64).copy()
        th[~np.isfinite(th)] = np.nan
        t.thresholds = th
        return t


class TreeLUTModel(Model):
    """TreeLUT (Khataei & Bazargan, FPGA 2025; MIT-licensed reference github.com/kiabuzz/TreeLUT):
    XGBoost on w_feature-bit unsigned inputs, leaves shifted by each tree's minimum and scaled by
    one global factor to w_tree-bit integers; score = integer sum of leaves (+ class bias)."""
    name = "treelut"

    def __init__(self, w_feature=8, w_tree=3, n_estimators=100, max_depth=4, learning_rate=0.3, **xgb):
        import xgboost
        self.wf, self.wt = w_feature, w_tree
        self.m = xgboost.XGBClassifier(n_estimators=n_estimators, max_depth=max_depth, learning_rate=learning_rate,
                                       tree_method="hist", n_jobs=4, eval_metric="logloss", **xgb)

    def _q(self, X):
        x = (X.astype(np.float64) - self.lo) * self.scale
        return np.clip(np.floor(x), 0, (1 << self.wf) - 1).astype(np.int32)

    def fit(self, X, y):
        self.lo = X.min(0).astype(np.float64)
        span = np.maximum(X.max(0).astype(np.float64) - self.lo, 1)
        self.scale = ((1 << self.wf) - 1) / span          # min-max to w_feature bits (training data only)
        self.m.fit(self._q(X), y)
        df = self.m.get_booster().trees_to_dataframe()
        self.trees = []
        leaves = df[df["Feature"] == "Leaf"]
        mins = leaves.groupby("Tree")["Gain"].min()
        rng = (leaves.groupby("Tree")["Gain"].max() - mins).max()
        self.leaf_scale = ((1 << self.wt) - 1) / rng
        # integer sum S maps back to logit units as S / leaf_scale + offset (per model, monotone);
        # a decision threshold th in those units is the integer threshold ceil((th - offset) * leaf_scale)
        self.offset = float(mins.sum())
        for t, g in df.groupby("Tree"):
            nodes = {}
            for _, r in g.iterrows():
                nid = int(r["ID"].split("-")[1])
                if r["Feature"] == "Leaf":
                    nodes[nid] = ("leaf", int(round((r["Gain"] - mins[t]) * self.leaf_scale)))
                else:
                    nodes[nid] = ("split", int(r["Feature"][1:]), int(np.ceil(r["Split"])),
                                  int(r["Yes"].split("-")[1]), int(r["No"].split("-")[1]))
            self.trees.append(nodes)
        return self

    def score(self, X):
        """Scores in logit units, so out-of-fold scores of different folds can be pooled."""
        return (self.score_int(X) / self.leaf_scale + self.offset).astype(np.float64)

    def int_threshold(self, th: float) -> int:
        return int(np.ceil((th - self.offset) * self.leaf_scale))

    def score_int(self, X):
        """Integer sum of quantised leaves: the value the hardware adder tree produces."""
        Q = self._q(X)
        total = np.zeros(len(Q), dtype=np.int64)
        for nodes in self.trees:
            cur = np.zeros(len(Q), dtype=np.int64)
            val = np.full(len(Q), -1, dtype=np.int64)
            for _ in range(32):
                todo = val < 0
                if not todo.any():
                    break
                for nid in np.unique(cur[todo]):
                    sel = todo & (cur == nid)
                    nd = nodes[nid]
                    if nd[0] == "leaf":
                        val[sel] = nd[1]
                    else:
                        go_yes = Q[sel, nd[1]] < nd[2]
                        idx = np.flatnonzero(sel)
                        cur[idx[go_yes]] = nd[3]
                        cur[idx[~go_yes]] = nd[4]
            total += val
        return total

    def cost(self, feature_bits):
        splits = {(nd[1], nd[2]) for t in self.trees for nd in t.values() if nd[0] == "split"}
        n_split = sum(1 for t in self.trees for nd in t.values() if nd[0] == "split")
        n_leaf = sum(1 for t in self.trees for nd in t.values() if nd[0] == "leaf")
        return hw.tree_cost(n_split, len(splits), n_leaf, len(self.trees), feature_bits=self.wf, leaf_bits=self.wt)


class LGNModel(Model):
    """Differentiable logic-gate network on thermometer bits (src/models/lgn.py)."""
    name = "lgn"

    def __init__(self, bits=8, layers=(2000, 2000), tau=10.0, epochs=20, lr=0.01, batch=2048, seed=0,
                 device="cpu", threads=4, log=None):
        self.p = dict(bits=bits, layers=tuple(layers), tau=tau, epochs=epochs, lr=lr, batch=batch, seed=seed,
                      device=device)
        self.threads, self.log = threads, (log or (lambda *a: None))

    def fit(self, X, y):
        import torch
        from .dwn import DistributiveThermometer
        from .lgn import LGN
        torch.set_num_threads(self.threads)
        p = self.p
        self.therm = DistributiveThermometer(p["bits"]).fit(X)
        bits = self.therm.encode(X)
        self.net = LGN(bits.shape[1], p["layers"], p["tau"], p["seed"])
        opt = torch.optim.Adam(self.net.parameters(), lr=p["lr"])
        yt = torch.as_tensor(y, dtype=torch.long)
        w = torch.tensor([1.0, float((y == 0).sum()) / max(1, int((y == 1).sum()))])
        g = torch.Generator().manual_seed(p["seed"])
        start = self._ckpt_load({"net": self.net}, opt, None, g)
        for ep in range(start, p["epochs"]):
            self.net.train()
            perm = torch.randperm(len(yt), generator=g)
            tot, t0 = 0.0, time.time()
            for i in range(0, len(perm), p["batch"]):
                idx = perm[i:i + p["batch"]]
                loss = torch.nn.functional.cross_entropy(self.net(bits[idx]), yt[idx], weight=w)
                opt.zero_grad()
                loss.backward()
                opt.step()
                tot += float(loss.detach()) * len(idx)
            self.log(f"    epoch {ep + 1}/{p['epochs']} loss {tot / len(perm):.4f} ({time.time() - t0:.0f} s)")
            self._ckpt_save(ep + 1, {"net": self.net}, opt, None, g)
        self.net.eval()
        self.exported = self.net.export()
        return self

    def score(self, X):
        from .lgn import lgn_integer_forward
        out = [lgn_integer_forward(self.therm.encode(X[i:i + 200_000]).numpy().astype(np.uint8), self.exported)
               for i in range(0, len(X), 200_000)]
        return np.concatenate(out).astype(np.float32)

    def cost(self, feature_bits):
        used = np.zeros(self.therm.n_bits, dtype=bool)
        first = self.exported["layers"][0]
        used[np.unique(np.concatenate([first["a"], first["b"]]))] = True
        t = self.therm.thresholds
        mask = used.reshape(t.shape)
        comps = sum(len(np.unique(t[f][mask[f]])) for f in range(t.shape[0]))
        enc = sum(len(np.unique(t[f][mask[f]])) * math.ceil(feature_bits[f] / 2) for f in range(t.shape[0]))
        gates = self.net.n_gates
        last = self.exported["layers"][-1]["op"].shape[0]
        return {"gates": int(gates), "network_luts_upper": int(gates), "encoder_comparators": int(comps),
                "encoder_luts": int(enc), "popcount_luts": int(last), "postproc_luts": hw.POSTPROC_LUTS,
                "total_luts": int(gates + enc + last + hw.POSTPROC_LUTS), "multipliers": 0}


class Int8MLPModel(Model):
    name = "mlp_int8"

    def __init__(self, hidden=(64, 32), epochs=20, lr=1e-3, batch=2048, seed=0, threads=4, log=None):
        self.p = dict(hidden=tuple(hidden), epochs=epochs, lr=lr, batch=batch, seed=seed)
        self.threads, self.log = threads, (log or (lambda *a: None))

    def _std(self, X):
        return torch_from((X.astype(np.float32) - self.mu) / self.sd)

    def fit(self, X, y):
        import torch
        from .mlp_int8 import Int8MLP
        torch.set_num_threads(self.threads)
        torch.manual_seed(self.p["seed"])
        self.mu = X.mean(0).astype(np.float32)
        self.sd = np.maximum(X.std(0), 1e-3).astype(np.float32)
        xs = self._std(X)
        self.net = Int8MLP(X.shape[1], self.p["hidden"])
        opt = torch.optim.Adam(self.net.parameters(), lr=self.p["lr"])
        yt = torch.as_tensor(y, dtype=torch.long)
        w = torch.tensor([1.0, float((y == 0).sum()) / max(1, int((y == 1).sum()))])
        g = torch.Generator().manual_seed(self.p["seed"])
        start = self._ckpt_load({"net": self.net}, opt, None, g)
        for ep in range(start, self.p["epochs"]):
            self.net.train()
            perm = torch.randperm(len(yt), generator=g)
            tot = 0.0
            for i in range(0, len(perm), self.p["batch"]):
                idx = perm[i:i + self.p["batch"]]
                loss = torch.nn.functional.cross_entropy(self.net(xs[idx]), yt[idx], weight=w)
                opt.zero_grad()
                loss.backward()
                opt.step()
                tot += float(loss.detach()) * len(idx)
            self.log(f"    epoch {ep + 1}/{self.p['epochs']} loss {tot / len(perm):.4f}")
            self._ckpt_save(ep + 1, {"net": self.net}, opt, None, g)
        self.net.eval()
        return self

    def score(self, X):
        import torch
        with torch.no_grad():
            out = [self.net(self._std(X[i:i + 200_000])) for i in range(0, len(X), 200_000)]
        o = torch.cat(out)
        return (o[:, 1] - o[:, 0]).numpy().astype(np.float32)

    def cost(self, feature_bits):
        return hw.mlp_cost(self.net.sizes)


class StatefulDWNModel(Model):
    """N1 (src/models/stateful.py), trained on sequences of consecutive windows."""
    name = "stateful_dwn"
    needs_store = True

    def __init__(self, bits=8, n_state=16, n_vote=200, hidden=None, n=6, mapping="learnable", tau=1 / 0.3,
                 seq_len=60, pos_per_seizure=6, neg_ratio=5, burn_in=10, epochs=15, lr=1e-2, batch=64,
                 decay_at=0.7, seed=0, threads=4, log=None):
        self.p = dict(bits=bits, n_state=n_state, n_vote=n_vote, hidden=hidden, n=n, mapping=mapping, tau=tau,
                      seq_len=seq_len, pos_per_seizure=pos_per_seizure, neg_ratio=neg_ratio, burn_in=burn_in,
                      epochs=epochs, lr=lr, batch=batch, decay_at=decay_at, seed=seed)
        self.threads, self.log = threads, (log or (lambda *a: None))

    def _sequences(self, store, subjects, cols, rng):
        """Training sequences: every start point is drawn from the labels alone, then each needed run is
        read once and only its sequences are kept (holding every training run in memory needed about
        14 GB for 77 patients and was killed by the out-of-memory killer). Same draws, same order and
        same values as reading all runs first."""
        T, bi, pps = self.p["seq_len"], self.p["burn_in"], self.p["pos_per_seizure"]
        keys = store.runs_of(subjects)
        ys = [store.load_labels(k) for k in keys]
        picks = []                                   # (run index, start) in draw order
        for i, y in enumerate(ys):
            pos = np.flatnonzero(y == 1)
            if len(pos) == 0 or len(y) < T:
                continue
            # one block of consecutive positive windows per seizure
            breaks = np.flatnonzero(np.diff(pos) > 1)
            for a, b in zip(np.r_[pos[0], pos[breaks + 1]], np.r_[pos[breaks], pos[-1]]):
                lo, hi = max(0, a - T + bi + 1), min(len(y) - T, b - bi)
                if hi < lo:
                    lo = hi = int(np.clip(a - T // 2, 0, len(y) - T))
                picks += [(i, int(st)) for st in rng.integers(lo, hi + 1, pps)]
        n_neg = self.p["neg_ratio"] * len(picks)
        lens = np.array([max(0, len(y) - T) for y in ys], dtype=float)
        for i in rng.choice(len(keys), size=n_neg, p=lens / lens.sum()):
            picks.append((int(i), int(rng.integers(0, len(ys[i]) - T))))
        by_run: dict[int, list] = {}
        for j, (i, st) in enumerate(picks):
            by_run.setdefault(i, []).append((j, st))
        Xs = Ys = None
        for i in sorted(by_run):
            r = store.load_run(keys[i])
            if Xs is None:
                Xs = np.empty((len(picks), T, len(cols)), dtype=r.X.dtype)
                Ys = np.empty((len(picks), T), dtype=r.y.dtype)
            for j, st in by_run[i]:
                Xs[j] = r.X[st:st + T][:, cols]
                Ys[j] = r.y[st:st + T]
        return Xs, Ys

    def _encode_u8(self, X, chunk=262_144):
        """Thermometer bits as uint8, encoded in row chunks (the float32 encoding of every training
        window at once is 4x larger)."""
        out = np.empty((len(X), self.therm.n_bits), dtype=np.uint8)
        for i in range(0, len(X), chunk):
            out[i:i + chunk] = self.therm.encode(X[i:i + chunk]).numpy()
        return out

    def fit_store(self, store, subjects, cols, seed):
        import torch
        from .dwn import DistributiveThermometer
        from .stateful import StatefulDWN
        torch.set_num_threads(self.threads)
        p = self.p
        rng = np.random.default_rng(seed)
        Xs, Ys = self._sequences(store, subjects, cols, rng)
        self.log(f"    {len(Xs)} sequences of {p['seq_len']} s ({int((Ys.sum(1) > 0).sum())} with seizure)")
        self.therm = DistributiveThermometer(p["bits"]).fit(Xs.reshape(-1, Xs.shape[-1]))
        B, T, F = Xs.shape
        bits = torch.from_numpy(self._encode_u8(Xs.reshape(-1, F))).reshape(B, T, -1)
        self.net = StatefulDWN(bits.shape[-1], p["n_state"], p["n_vote"], p["n"], p["mapping"], p["tau"], p["hidden"], seed)
        opt = torch.optim.Adam(self.net.parameters(), lr=p["lr"])
        sched = torch.optim.lr_scheduler.StepLR(opt, max(1, int(p["epochs"] * p["decay_at"])), 0.1)
        yt = torch.as_tensor(Ys, dtype=torch.long)
        bi = p["burn_in"]
        w = torch.tensor([1.0, float((Ys[:, bi:] == 0).sum()) / max(1, int((Ys[:, bi:] == 1).sum()))])
        g = torch.Generator().manual_seed(seed)
        start = self._ckpt_load({"net": self.net}, opt, sched, g)
        for ep in range(start, p["epochs"]):
            self.net.train()
            perm = torch.randperm(B, generator=g)
            tot, t0 = 0.0, time.time()
            for i in range(0, B, p["batch"]):
                idx = perm[i:i + p["batch"]]
                logits, _ = self.net(bits[idx].float())
                loss = torch.nn.functional.cross_entropy(logits[:, bi:].reshape(-1, 2), yt[idx, bi:].reshape(-1), weight=w)
                opt.zero_grad()
                loss.backward()
                opt.step()
                tot += float(loss.detach()) * len(idx)
            sched.step()
            self.log(f"    epoch {ep + 1}/{p['epochs']} loss {tot / B:.4f} ({time.time() - t0:.0f} s)")
            self._ckpt_save(ep + 1, {"net": self.net}, opt, sched, g)
        self.net.eval()
        self.exported = self.net.export()
        return self

    def score_runs(self, X_list, group=32):
        """Integer scores per run. Runs are independent (the state starts at zero in each), so they are
        scored in groups of similar length to bound memory; the result does not depend on `group`."""
        from .stateful import batched_integer_forward
        order = np.argsort([len(X) for X in X_list], kind="stable")
        out = [None] * len(X_list)
        for g in range(0, len(order), group):
            idx = order[g:g + group]
            for i, s in zip(idx, batched_integer_forward([self._encode_u8(X_list[i]) for i in idx], self.exported)):
                out[i] = s.astype(np.float32)
        return out

    def score(self, X):
        return self.score_runs([X])[0]

    def cost(self, feature_bits):
        from .dwn import used_input_bits
        n_in = self.therm.n_bits
        first = self.exported["layers"][0]["mapping"]
        used = np.zeros(n_in, dtype=bool)
        used[np.unique(first[first < n_in])] = True
        c = hw.dwn_cost({"layers": [{"mapping": l["mapping"]} for l in self.exported["layers"]]}, self.therm,
                        list(feature_bits), used)
        c["state_flipflops"] = self.p["n_state"]
        return c


class GRUFeatureModel(StatefulDWNModel):
    """GRU on the same per-window features (N1's upper reference, Section 6.3): the same training
    sequences as N1, standardised features, one GRU layer and a linear head; at inference the state
    runs through each whole recording, like N1's state bits. Multiplier-based (cost in MACs)."""
    name = "gru"
    needs_store = True

    def __init__(self, hidden=32, seq_len=60, pos_per_seizure=6, neg_ratio=5, burn_in=10, epochs=15, lr=1e-3,
                 batch=64, decay_at=0.7, seed=0, threads=4, log=None):
        self.p = dict(hidden=hidden, seq_len=seq_len, pos_per_seizure=pos_per_seizure, neg_ratio=neg_ratio,
                      burn_in=burn_in, epochs=epochs, lr=lr, batch=batch, decay_at=decay_at, seed=seed)
        self.threads, self.log = threads, (log or (lambda *a: None))

    def _std(self, X):
        return (np.asarray(X, dtype=np.float32) - self.mu) / self.sd

    def fit_store(self, store, subjects, cols, seed):
        import torch
        torch.set_num_threads(self.threads)
        torch.manual_seed(seed)
        p = self.p
        Xs, Ys = self._sequences(store, subjects, cols, np.random.default_rng(seed))
        self.log(f"    {len(Xs)} sequences of {p['seq_len']} s ({int((Ys.sum(1) > 0).sum())} with seizure)")
        flat = Xs.reshape(-1, Xs.shape[-1]).astype(np.float32)
        self.mu, self.sd = flat.mean(0), np.maximum(flat.std(0), 1e-3).astype(np.float32)
        x = torch.from_numpy(self._std(Xs))
        self.gru = torch.nn.GRU(x.shape[-1], p["hidden"], batch_first=True)
        self.head = torch.nn.Linear(p["hidden"], 2)
        params = list(self.gru.parameters()) + list(self.head.parameters())
        opt = torch.optim.Adam(params, lr=p["lr"])
        sched = torch.optim.lr_scheduler.StepLR(opt, max(1, int(p["epochs"] * p["decay_at"])), 0.1)
        yt = torch.as_tensor(Ys, dtype=torch.long)
        bi = p["burn_in"]
        w = torch.tensor([1.0, float((Ys[:, bi:] == 0).sum()) / max(1, int((Ys[:, bi:] == 1).sum()))])
        g = torch.Generator().manual_seed(seed)
        mods = {"gru": self.gru, "head": self.head}
        start = self._ckpt_load(mods, opt, sched, g)
        B = len(x)
        for ep in range(start, p["epochs"]):
            self.gru.train()
            perm = torch.randperm(B, generator=g)
            tot, t0 = 0.0, time.time()
            for i in range(0, B, p["batch"]):
                idx = perm[i:i + p["batch"]]
                h, _ = self.gru(x[idx])
                logits = self.head(h[:, bi:])
                loss = torch.nn.functional.cross_entropy(logits.reshape(-1, 2), yt[idx, bi:].reshape(-1), weight=w)
                opt.zero_grad()
                loss.backward()
                opt.step()
                tot += float(loss.detach()) * len(idx)
            sched.step()
            self.log(f"    epoch {ep + 1}/{p['epochs']} loss {tot / B:.4f} ({time.time() - t0:.0f} s)")
            self._ckpt_save(ep + 1, mods, opt, sched, g)
        self.gru.eval()
        self.n_in = x.shape[-1]
        return self

    def score_runs(self, X_list, chunk=20_000):
        import torch
        out = []
        with torch.no_grad():
            for X in X_list:
                h, s = None, []
                xs = torch.from_numpy(self._std(X))[None]
                for i in range(0, xs.shape[1], chunk):       # the state carries across chunks
                    o, h = self.gru(xs[:, i:i + chunk], h)
                    lg = self.head(o[0])
                    s.append((lg[:, 1] - lg[:, 0]).numpy())
                out.append(np.concatenate(s).astype(np.float32) if s else np.zeros(0, np.float32))
        return out

    def cost(self, feature_bits):
        H, F = self.p["hidden"], self.n_in
        macs = 3 * (F * H + H * H) + 2 * H
        return {"macs": int(macs), "weights": int(3 * (F * H + H * H + 2 * H) + 2 * H + 2), "multipliers": int(macs)}


class LogicNetModel(Model):
    """LogicNets-style sparse quantized MLP (src/models/logicnets.py), Tier-1 LUT-native family.
    score() is the integer difference of the two output halves' activation codes."""
    name = "logicnet"

    def __init__(self, hidden=(128, 64, 32), fan_in=3, act_bits=2, in_bits=2, tau=1.0, epochs=30, lr=1e-2,
                 batch=4096, decay_at=0.7, seed=0, device="cpu", threads=4, log=None):
        self.p = dict(hidden=tuple(hidden), fan_in=fan_in, act_bits=act_bits, in_bits=in_bits, tau=tau,
                      epochs=epochs, lr=lr, batch=batch, decay_at=decay_at, seed=seed, device=device)
        self.threads, self.log = threads, (log or (lambda *a: None))

    def _codes(self, X):
        import torch
        c = np.zeros(X.shape, dtype=np.int64)
        for j in range(self.thresholds.shape[1]):
            c += X > self.thresholds[:, j][None, :]
        return torch.from_numpy(c)

    def fit(self, X, y, **_):
        import torch
        from .logicnets import LogicNet
        torch.set_num_threads(self.threads)
        p = self.p
        torch.manual_seed(p["seed"])
        q = np.arange(1, 2 ** p["in_bits"]) / 2 ** p["in_bits"]
        self.thresholds = np.floor(np.quantile(X.astype(np.float64), q, axis=0).T)   # (features, levels-1)
        dev = torch.device(p["device"])
        codes = self._codes(X)
        self.net = LogicNet(X.shape[1], p["hidden"], p["fan_in"], p["act_bits"], p["in_bits"], p["tau"], p["seed"]).to(dev)
        opt = torch.optim.Adam(self.net.parameters(), lr=p["lr"])
        sched = torch.optim.lr_scheduler.StepLR(opt, step_size=max(1, int(p["epochs"] * p["decay_at"])), gamma=0.1)
        yt = torch.as_tensor(y, dtype=torch.long)
        w = torch.tensor([1.0, float((y == 0).sum()) / max(1, int((y == 1).sum()))], device=dev)
        g = torch.Generator().manual_seed(p["seed"])
        start = self._ckpt_load({"net": self.net}, opt, sched, g)
        for ep in range(start, p["epochs"]):
            self.net.train()
            perm = torch.randperm(len(yt), generator=g)
            tot, t0 = 0.0, time.time()
            for i in range(0, len(perm), p["batch"]):
                idx = perm[i:i + p["batch"]]
                logits, _ = self.net(codes[idx].to(dev))
                loss = torch.nn.functional.cross_entropy(logits, yt[idx].to(dev), weight=w)
                opt.zero_grad()
                loss.backward()
                opt.step()
                tot += float(loss.detach()) * len(idx)
            sched.step()
            self.log(f"    epoch {ep + 1}/{p['epochs']} loss {tot / len(perm):.4f} ({time.time() - t0:.0f} s)")
            self._ckpt_save(ep + 1, {"net": self.net}, opt, sched, g)
        self.net.eval().cpu()
        return self

    def score(self, X):
        import torch
        out = []
        with torch.no_grad():
            for i in range(0, len(X), 200_000):
                out.append(self.net(self._codes(X[i:i + 200_000]))[1].numpy())
        return np.concatenate(out).astype(np.float32)

    def cost(self, feature_bits):
        c = self.net.lut_cost()
        comps = comp_bits = enc = 0
        for f in self.net.used_inputs():
            k = len(np.unique(self.thresholds[f]))
            comps += k
            comp_bits += k * feature_bits[f]
            enc += k * math.ceil(feature_bits[f] / 2)
        total = c["network_luts"] + c["adder_luts"] + enc + hw.POSTPROC_LUTS
        return {**c, "encoder_comparators": int(comps), "encoder_comparator_bits": int(comp_bits),
                "encoder_luts": int(enc), "postproc_luts": hw.POSTPROC_LUTS, "total_luts": int(total), "multipliers": 0}


def torch_from(a):
    import torch
    return torch.from_numpy(np.ascontiguousarray(a))


class LateFusionDWN(Model):
    """N6 late fusion: one DWN per modality, integer scores added (Section 6.3).

    Expects every cached feature column in spec order (config `features: all`). Each group takes
    the columns whose names start with its prefixes, optionally keeps the top `mi_top` of them by
    mutual information on the training data, and trains its own DWN with the shared parameters and
    its own `layers`. score = sum of the groups' popcount differences (an integer).
    """
    name = "dwn_late"
    GROUPS = {"eeg": {"prefix": ["eeg_"], "mi_top": 30, "layers": [120]},
              "ecg": {"prefix": ["ecg_", "present_ecg"], "layers": [20]},
              "emg": {"prefix": ["emg_", "present_emg"], "layers": [30]},
              "mov": {"prefix": ["mov_", "present_mov_acc", "present_mov_gyr"], "layers": [30]}}

    def __init__(self, groups=None, log=None, threads=4, **dwn_params):
        self.groups = groups or self.GROUPS
        self.dwn_params = dwn_params
        self.threads = threads
        self.log = log or (lambda *a: None)
        self.p = {"seed": dwn_params.get("seed", 0)}       # the CV runner sets p["seed"] per fold

    def _columns(self, n_cols):
        from ..features import spec as S
        if n_cols != len(S.FEATURES):
            raise ValueError(f"dwn_late needs every feature column in spec order (features: all), got {n_cols}")
        return {g: [i for i, n in enumerate(S.FEATURES) if n.startswith(tuple(c["prefix"]))]
                for g, c in self.groups.items()}

    def fit(self, X, y, **fit_kw):
        from sklearn.feature_selection import mutual_info_classif
        cols = self._columns(X.shape[1])
        rs = np.random.default_rng(self.p["seed"])
        self.cols, self.models = {}, {}
        for g, c in self.groups.items():
            gc = cols[g]
            if c.get("mi_top") and c["mi_top"] < len(gc):
                sub = rs.choice(len(y), size=min(len(y), 200_000), replace=False)
                mi = mutual_info_classif(X[sub][:, gc].astype(np.float32), y[sub], random_state=self.p["seed"])
                gc = [gc[i] for i in np.argsort(-mi)[: c["mi_top"]]]
            params = {**self.dwn_params, "layers": c["layers"], "seed": self.p["seed"]}
            m = DWNModel(**params, threads=self.threads, log=self.log)
            m.ckpt_path = f"{self.ckpt_path}.{g}" if self.ckpt_path else None
            self.log(f"  late fusion: {g} DWN {c['layers']} on {len(gc)} features")
            m.fit(np.ascontiguousarray(X[:, gc]), y, **fit_kw)
            self.cols[g], self.models[g] = gc, m
        if self.ckpt_path:
            from pathlib import Path
            for g in self.groups:
                Path(f"{self.ckpt_path}.{g}").unlink(missing_ok=True)
        return self

    def __getstate__(self):
        # the run log is a closure: drop it (and the sub-models' copies) when the model is pickled
        import copy
        st = {**self.__dict__, "log": None}
        if "models" in st:
            st["models"] = {g: copy.copy(m) for g, m in st["models"].items()}
            for m in st["models"].values():
                m.log = None
        return st

    def score_groups(self, X) -> dict:
        return {g: m.score(np.ascontiguousarray(X[:, self.cols[g]])) for g, m in self.models.items()}

    def score(self, X):
        return np.sum(list(self.score_groups(X).values()), axis=0).astype(np.float32)

    def cost(self, feature_bits):
        fb = list(feature_bits)
        per = {g: m.cost([fb[i] for i in self.cols[g]]) for g, m in self.models.items()}
        out = {k: int(sum(c[k] for c in per.values())) for k in next(iter(per.values()))
               if k not in ("postproc_luts", "total_luts")}
        # adding the group scores: one adder per extra group, as wide as the largest score
        width = max(int(np.ceil(np.log2(sum(m.p["layers"][-1] for m in self.models.values()) + 1))) + 1, 2)
        out["fusion_adder_luts"] = width * (len(self.models) - 1)
        out["postproc_luts"] = hw.POSTPROC_LUTS
        out["total_luts"] = int(sum(c["total_luts"] - c["postproc_luts"] for c in per.values())
                                + out["fusion_adder_luts"] + hw.POSTPROC_LUTS)
        return out


REGISTRY = {c.name: c for c in (LogReg, LightGBM, XGBoost, CatBoost, RandomForest, DWNModel, TreeLUTModel, LGNModel,
                                Int8MLPModel, StatefulDWNModel, LateFusionDWN, GRUFeatureModel,
                                LogicNetModel)}


def build(spec: dict, log=None) -> Model:
    cls = REGISTRY[spec["type"]]
    params = dict(spec.get("params", {}))
    import inspect
    if "log" in inspect.signature(cls.__init__).parameters:
        params["log"] = log             # every trainable family reports its epochs in the run log
    return cls(**params)
