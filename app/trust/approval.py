"""Human approval / correction: the moment the flywheel captures a fact into the knowledge graph.

Every decision (approve or correct) finalizes the categorization, writes a `CODED_TO` fact into the
graph for (vendor, client) (invalidating any prior fact), and appends to the tamper-evident audit log.
"""
from __future__ import annotations

from typing import Optional

from .. import db
from ..kg.store import get_store
from . import audit


def apply_approval(firm_id: str, transaction_id: str, action: str, accounts: list[dict],
                   corrected_code: Optional[str] = None, approver: str = "demo-cpa") -> dict:
    cat = db.get_categorization(transaction_id)
    if cat is None:
        raise ValueError(f"no categorization for {transaction_id}")
    tx = db.get_transaction(transaction_id)

    if action == "correct":
        if not corrected_code:
            raise ValueError("corrected_code required for a correction")
        final_code = corrected_code
        cat["status"] = "corrected"
    elif action == "approve":
        final_code = cat["predicted_code"]
        cat["status"] = "approved"
    else:
        raise ValueError(f"unknown action {action}")

    cat["final_code"] = final_code
    db.save_categorization(cat)

    # Write the human-validated fact into the knowledge graph (the flywheel).
    vendor_id = cat.get("vendor_id")
    if vendor_id:
        get_store().set_coded_to(firm_id, vendor_id, tx["client_id"], final_code,
                                 confidence=0.97, source=f"{action}:{transaction_id}")

    audit.record(approver, action, {
        "transaction_id": transaction_id, "predicted_code": cat["predicted_code"],
        "final_code": final_code, "was_model_correct": cat["predicted_code"] == final_code,
    }, firm_id=firm_id)
    return cat
