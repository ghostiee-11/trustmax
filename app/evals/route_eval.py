"""Routing eval. The headline is the MISROUTE RATE among auto-routed documents: it must be ~0,
because routing a document to the wrong client is a confidentiality breach.

Run: `python -m app.evals.route_eval --firm firm00`
"""
from __future__ import annotations

import argparse
import json

from .. import db
from ..agents.router_agent import RouterAgent
from ..config import AUTO_ROUTE_THRESHOLD


def evaluate(firm_id: str) -> dict:
    agent = RouterAgent(firm_id)
    docs = db.get_documents(firm_id)
    n = len(docs)
    correct = auto = auto_wrong = resolved = 0
    for d in docs:
        res = agent.route(d)
        pred = res["client_id"]
        gt = d["gt_client_id"]
        if pred is not None:
            resolved += 1
            if pred == gt:
                correct += 1
        if pred is not None and res["confidence"] >= AUTO_ROUTE_THRESHOLD:
            auto += 1
            if pred != gt:
                auto_wrong += 1
    return {
        "firm_id": firm_id, "documents": n,
        "overall_accuracy": round(correct / n, 4) if n else 0.0,
        "accuracy_when_resolved": round(correct / resolved, 4) if resolved else 0.0,
        "auto_route_rate": round(auto / n, 4) if n else 0.0,
        "misroute_rate_of_auto": round(auto_wrong / auto, 4) if auto else 0.0,
        "human_review_rate": round((n - auto) / n, 4) if n else 0.0,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--firm", default="firm00")
    ap.add_argument("--all", action="store_true", help="aggregate across all firms")
    args = ap.parse_args()
    firms = [f["id"] for f in db.get_firms()] if args.all else [args.firm]
    for fid in firms:
        print(json.dumps(evaluate(fid)))


if __name__ == "__main__":
    main()
