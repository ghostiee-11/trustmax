"""Code flywheel eval: prove that graph-native learning raises accuracy and safe autonomy over time.

For one firm we run its monthly batches in order. Between batches a simulated reviewer (using ground
truth) approves or corrects pending items, which writes CODED_TO facts into the knowledge graph. Each
later batch retrieves those facts via GraphRAG, so accuracy and the auto-approve rate climb while the
auto-approved error rate stays low (safe autonomy).

Run: `python -m app.evals.code_eval --firm firm00`
"""
from __future__ import annotations

import argparse
import json
from typing import Optional

from .. import config, db
from ..agents import code_agent
from ..kg import retrieval
from ..kg.store import get_store
from ..trust import approval


def evaluate_batch(firm_id: str, batch_id: str) -> dict:
    cats = db.get_categorizations(firm_id, batch_id)
    txns = {t["id"]: t for t in db.get_transactions(firm_id, batch_id=batch_id)}
    n = len(cats)
    if n == 0:
        return {"batch_id": batch_id, "n": 0}
    correct = auto = auto_err = grounded = 0
    for c in cats:
        gt = txns[c["transaction_id"]]["gt_code"]
        ok = c["predicted_code"] == gt
        correct += int(ok)
        grounded += int(c.get("graph_support", 0) > 0)
        if c["decision"] == "auto_approve":
            auto += 1
            auto_err += int(not ok)
    return {
        "batch_id": batch_id, "n": n,
        "accuracy": round(correct / n, 4),
        "auto_approve_rate": round(auto / n, 4),
        "auto_approved_error_rate": round((auto_err / auto) if auto else 0.0, 4),
        "graph_grounded_rate": round(grounded / n, 4),
    }


def oracle_review(firm_id: str, batch_id: str) -> dict:
    accounts = db.get_gl_accounts(firm_id)
    approved = corrected = 0
    for c in db.get_categorizations(firm_id, batch_id):
        if c["status"] != "pending":
            continue
        gt = db.get_transaction(c["transaction_id"])["gt_code"]
        if c["predicted_code"] == gt:
            approval.apply_approval(firm_id, c["transaction_id"], "approve", accounts, approver="oracle-cpa")
            approved += 1
        else:
            approval.apply_approval(firm_id, c["transaction_id"], "correct", accounts,
                                    corrected_code=gt, approver="oracle-cpa")
            corrected += 1
    return {"approved": approved, "corrected": corrected}


def run(firm_id: str, limit_per_batch: Optional[int] = None) -> list[dict]:
    get_store().clear_coded_to(firm_id)   # start with nothing learned, so the curve is real
    retrieval.reset_cache()
    rows = []
    for batch_id in db.list_batches(firm_id):
        code_agent.run_batch(firm_id, batch_id, limit=limit_per_batch)
        m = evaluate_batch(firm_id, batch_id)
        db.save_eval_run("code", batch_id, m)
        rev = oracle_review(firm_id, batch_id)
        m["human_corrected"] = rev["corrected"]
        rows.append(m)
        print(f"  {batch_id}: acc={m['accuracy']*100:5.1f}%  auto={m['auto_approve_rate']*100:5.1f}%  "
              f"auto-err={m['auto_approved_error_rate']*100:4.1f}%  grounded={m['graph_grounded_rate']*100:5.1f}%  "
              f"(human corrected {rev['corrected']})")
    if len(rows) >= 2:
        a, b = rows[0], rows[-1]
        print(f"\n  Flywheel: accuracy {a['accuracy']*100:.1f}% -> {b['accuracy']*100:.1f}%   "
              f"auto-approve {a['auto_approve_rate']*100:.1f}% -> {b['auto_approve_rate']*100:.1f}%   "
              f"(auto-error stays {b['auto_approved_error_rate']*100:.1f}%)")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--firm", default="firm00")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    from ..providers import get_provider
    print(f"Code flywheel eval | firm={args.firm} | provider={get_provider().name}")
    print("=" * 78)
    rows = run(args.firm, args.limit)
    (config.DATA_DIR / "code_scorecard.json").write_text(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
