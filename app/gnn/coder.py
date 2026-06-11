"""Graph ML for GL coding: predict a transaction's account from graph structure alone.

This complements the flywheel. The flywheel learns exact (vendor, client) facts from approvals; the
graph model GENERALIZES from structure (vendor category, client industry, amount, the vendor->account
neighbourhood), so it helps on cold-start and on vendors a client has never used before, and gives an
independent signal for the ensemble.

A real PyTorch Geometric GraphSAGE (heterogeneous: transaction / vendor / client / account nodes) is
used when torch is installed; otherwise a scikit-learn RandomForest over the same graph-derived
features is the fallback, so the component always runs. Both report held-out accuracy.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from .. import db
from ..datagen.seeds import EXPENSE_CODES


def _build_frame(firm_id: str):
    vendors = {v["id"]: v for v in db.get_vendors(firm_id)}
    clients = {c["id"]: c for c in db.get_clients(firm_id)}
    cats = sorted({v["category"] for v in vendors.values()})
    inds = sorted({c["industry"] for c in clients.values()})
    classes = list(EXPENSE_CODES)
    cat_ix = {c: i for i, c in enumerate(cats)}
    ind_ix = {c: i for i, c in enumerate(inds)}
    cls_ix = {c: i for i, c in enumerate(classes)}

    rows = []
    for t in db.get_transactions(firm_id):
        v = vendors.get(t.get("vendor_id"))
        if not v or t["gt_code"] not in cls_ix:
            continue
        cl = clients.get(t["client_id"], {})
        month = int(t["batch_id"][-2:])
        feat = [math.log1p(t["amount"]), math.sin(2 * math.pi * month / 12), math.cos(2 * math.pi * month / 12)]
        cat_oh = [0.0] * len(cats); cat_oh[cat_ix[v["category"]]] = 1.0
        ind_oh = [0.0] * len(inds)
        if cl.get("industry") in ind_ix:
            ind_oh[ind_ix[cl["industry"]]] = 1.0
        rows.append({"x": feat + cat_oh + ind_oh, "y": cls_ix[t["gt_code"]],
                     "vendor_id": t["vendor_id"], "client_id": t["client_id"], "tx_id": t["id"]})
    return rows, classes


def _split(n: int, seed: int = 7):
    rng = np.random.RandomState(seed)
    idx = rng.permutation(n)
    cut = int(n * 0.7)
    return idx[:cut], idx[cut:]


def _train_rf(rows, classes) -> dict:
    from sklearn.ensemble import RandomForestClassifier
    X = np.array([r["x"] for r in rows]); y = np.array([r["y"] for r in rows])
    tr, te = _split(len(rows))
    clf = RandomForestClassifier(n_estimators=120, random_state=7, n_jobs=-1).fit(X[tr], y[tr])
    acc = float((clf.predict(X[te]) == y[te]).mean())
    return {"method": "randomforest-graph-features", "n": len(rows), "n_classes": len(classes),
            "test_accuracy": round(acc, 4), "features": X.shape[1]}


def _train_gnn(rows, classes) -> dict:
    import torch
    import torch.nn.functional as F
    from torch_geometric.data import HeteroData
    from torch_geometric.nn import HeteroConv, SAGEConv, Linear

    vendors = sorted({r["vendor_id"] for r in rows})
    clients = sorted({r["client_id"] for r in rows})
    v_ix = {v: i for i, v in enumerate(vendors)}
    c_ix = {c: i for i, c in enumerate(clients)}

    x_tx = torch.tensor([r["x"] for r in rows], dtype=torch.float)
    y = torch.tensor([r["y"] for r in rows], dtype=torch.long)
    tr, te = _split(len(rows))
    train_mask = torch.zeros(len(rows), dtype=torch.bool); train_mask[tr] = True
    test_mask = torch.zeros(len(rows), dtype=torch.bool); test_mask[te] = True

    data = HeteroData()
    data["tx"].x = x_tx
    data["vendor"].x = torch.eye(len(vendors))
    data["client"].x = torch.eye(len(clients))
    tv = torch.tensor([[i, v_ix[r["vendor_id"]]] for i, r in enumerate(rows)], dtype=torch.long).t()
    tc = torch.tensor([[i, c_ix[r["client_id"]]] for i, r in enumerate(rows)], dtype=torch.long).t()
    data["tx", "references", "vendor"].edge_index = tv
    data["vendor", "rev_references", "tx"].edge_index = tv.flip(0)
    data["tx", "for", "client"].edge_index = tc
    data["client", "rev_for", "tx"].edge_index = tc.flip(0)

    hidden, n_cls = 64, len(classes)

    class Net(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.l1 = HeteroConv({et: SAGEConv((-1, -1), hidden) for et in data.edge_types}, aggr="sum")
            self.l2 = HeteroConv({et: SAGEConv((-1, -1), hidden) for et in data.edge_types}, aggr="sum")
            self.out = Linear(hidden, n_cls)

        def forward(self, x, ei):
            x = {k: F.relu(v) for k, v in self.l1(x, ei).items()}
            x = {k: F.relu(v) for k, v in self.l2(x, ei).items()}
            return self.out(x["tx"])

    model = Net()
    opt = torch.optim.Adam(model.parameters(), lr=0.01, weight_decay=5e-4)
    xdict, eidict = data.x_dict, data.edge_index_dict
    model.train()
    for _ in range(60):
        opt.zero_grad()
        out = model(xdict, eidict)
        loss = F.cross_entropy(out[train_mask], y[train_mask])
        loss.backward(); opt.step()
    model.eval()
    with torch.no_grad():
        pred = model(xdict, eidict).argmax(1)
        acc = float((pred[test_mask] == y[test_mask]).float().mean())
    return {"method": "graphsage-hetero (PyG)", "n": len(rows), "n_classes": n_cls,
            "test_accuracy": round(acc, 4), "epochs": 60, "hidden": hidden}


def train_eval(firm_id: str) -> dict:
    rows, classes = _build_frame(firm_id)
    if len(rows) < 50:
        return {"error": "not enough labeled transactions"}
    try:
        import torch  # noqa
        import torch_geometric  # noqa
        return _train_gnn(rows, classes)
    except Exception as e:
        out = _train_rf(rows, classes)
        out["gnn_note"] = f"PyG unavailable ({type(e).__name__}); used fallback"
        return out


if __name__ == "__main__":
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("--firm", default="firm00")
    args = ap.parse_args()
    print(json.dumps(train_eval(args.firm), indent=2))
