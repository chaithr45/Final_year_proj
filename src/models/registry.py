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
    """Thermometer + DWN (src/models/dwn.py), trained with class-weighted cross-entropy.
    score() is the INTEGER popcount difference of the exported network (hardware-exact)."""
    name = "dwn"

    def __init__(self, bits=8, layers=(200,), n=6, mapping="learnable", tau=1 / 0.3, epochs=30, lr=1e-2,
                 batch=2048, decay_at=0.7, loss="ce", focal_gamma=2.0, seed=0, device="cpu", threads=4,
                 log=None):
        self.p = dict(bits=bits, layers=tuple(layers), n=n, mapping=mapping, tau=tau, epochs=epochs, lr=lr,
                      batch=batch, decay_at=decay_at, loss=loss, focal_gamma=focal_gamma, seed=seed, device=device)
        self.threads = threads
        self.log = log or (lambda *a: None)

    def fit(self, X, y):
        import torch
        from .dwn import DWN, DistributiveThermometer
        torch.set_num_threads(self.threads)
        p = self.p
        self.therm = DistributiveThermometer(p["bits"]).fit(X)
        bits = self.therm.encode(X)
        dev = torch.device(p["device"])
        self.net = DWN(bits.shape[1], p["layers"], p["n"], p["mapping"], p["tau"], p["seed"]).to(dev)
        opt = torch.optim.Adam(self.net.parameters(), lr=p["lr"])
        sched = torch.optim.lr_scheduler.StepLR(opt, step_size=max(1, int(p["epochs"] * p["decay_at"])), gamma=0.1)
        yt = torch.as_tensor(y, dtype=torch.long)
        w = torch.tensor([1.0, float((y == 0).sum()) / max(1, int((y == 1).sum()))], device=dev)
        g = torch.Generator().manual_seed(p["seed"])
        for ep in range(p["epochs"]):
            self.net.train()
            perm = torch.randperm(len(yt), generator=g)
            tot, t0 = 0.0, time.time()
            for i in range(0, len(perm), p["batch"]):
                idx = perm[i:i + p["batch"]]
                xb, yb = bits[idx].to(dev), yt[idx].to(dev)
                out = self.net(xb)
                if p["loss"] == "focal":
                    logp = torch.log_softmax(out, 1)
                    pt = logp.gather(1, yb[:, None]).squeeze(1).exp()
                    loss = (-(1 - pt) ** p["focal_gamma"] * logp.gather(1, yb[:, None]).squeeze(1) * w[yb]).mean()
                else:
                    loss = torch.nn.functional.cross_entropy(out, yb, weight=w)
                opt.zero_grad()
                loss.backward()
                opt.step()
                tot += float(loss.detach()) * len(idx)
            sched.step()
            self.log(f"    epoch {ep + 1}/{p['epochs']} loss {tot / len(perm):.4f} ({time.time() - t0:.0f} s)")
        self.net.eval()
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
        return hw.dwn_cost(self.exported, self.therm, list(feature_bits), used)


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
        return total.astype(np.float32)

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
        for ep in range(p["epochs"]):
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


REGISTRY = {c.name: c for c in (LogReg, LightGBM, XGBoost, CatBoost, RandomForest, DWNModel, TreeLUTModel, LGNModel)}


def build(spec: dict, log=None) -> Model:
    cls = REGISTRY[spec["type"]]
    params = dict(spec.get("params", {}))
    if cls is DWNModel:
        params["log"] = log
    return cls(**params)
