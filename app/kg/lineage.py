"""Lineage: 'explain this number'.

Given a transaction, return the full provenance: the decision, the graph reasoning path that produced
it, the current learned fact, the source document, and every audit-log event that touched it. This is
the white-box trust surface a CPA (or the IRS) needs.
"""
from __future__ import annotations

import json
from typing import Any

from .. import db
from ..trust import audit
from .store import get_store


def explain(firm_id: str, transaction_id: str) -> dict[str, Any]:
    tx = db.get_transaction(transaction_id)
    if not tx or tx["firm_id"] != firm_id:
        return {"error": "transaction not found in this firm"}
    cat = db.get_categorization(transaction_id) or {}

    # audit events that reference this transaction
    events = []
    for row in audit.get_log():
        try:
            payload = json.loads(row["payload"])
        except Exception:
            payload = {}
        if payload.get("transaction_id") == transaction_id:
            events.append({"seq": row["seq"], "ts": row["ts"], "actor": row["actor"],
                           "action": row["action"], "payload": payload})

    return {
        "transaction": {
            "id": tx["id"], "client_id": tx["client_id"], "date": tx["date"],
            "vendor_raw": tx["vendor_raw"], "amount": tx["amount"],
            "source": tx["source_span"],
        },
        "decision": {
            "code": cat.get("final_code") or cat.get("predicted_code"),
            "account": cat.get("predicted_account_name"),
            "calibrated_confidence": cat.get("calibrated_confidence"),
            "status": cat.get("status"),
            "grounded": cat.get("graph_support", 0) > 0,
        },
        "reasoning_path": cat.get("reasoning_path", []),
        "graph_fact": get_store().reasoning_path(firm_id, transaction_id).get("graph_fact"),
        "audit_trail": events,
    }
