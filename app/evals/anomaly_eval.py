"""Anomaly detection eval: precision / recall against the labeled injected anomalies.

Run: `python -m app.evals.anomaly_eval --firm firm00`
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict

from .. import db
from ..agents.anomaly_agent import detect


def evaluate(firm_id: str) -> dict:
    txns = {t["id"]: t for t in db.get_transactions(firm_id)}
    alerts = detect(firm_id)
    flagged: dict[str, set] = defaultdict(set)
    for a in alerts:
        flagged[a["type"]].add(a["transaction_id"])

    truth: dict[str, set] = defaultdict(set)
    for t in txns.values():
        if t.get("is_anomaly") and t.get("anomaly_type"):
            truth[t["anomaly_type"]].add(t["id"])

    out = {"firm_id": firm_id, "per_type": {}}
    all_pred, all_true = set(), set()
    for atype in ["duplicate", "unusual_amount", "missing_category"]:
        pred, gt = flagged.get(atype, set()), truth.get(atype, set())
        tp = len(pred & gt)
        prec = tp / len(pred) if pred else 0.0
        rec = tp / len(gt) if gt else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        out["per_type"][atype] = {"predicted": len(pred), "actual": len(gt),
                                  "precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3)}
        all_pred |= pred
        all_true |= gt
    tp = len(all_pred & all_true)
    out["overall"] = {
        "predicted": len(all_pred), "actual": len(all_true),
        "precision": round(tp / len(all_pred), 3) if all_pred else 0.0,
        "recall": round(tp / len(all_true), 3) if all_true else 0.0,
    }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--firm", default="firm00")
    args = ap.parse_args()
    print(json.dumps(evaluate(args.firm), indent=2))


if __name__ == "__main__":
    main()
