"""Append-only, hash-chained audit log.

Every agent decision and every human action is recorded as a row whose hash commits to the previous
row's hash, forming a tamper-evident chain (a tiny blockchain). In accounting "the work is the
evidence", so the audit trail is a first-class product surface, not an afterthought. `verify_chain`
recomputes the chain end to end; editing any historical row breaks it.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from ..db import connect

GENESIS = "0" * 64


def _canonical(ts: str, actor: str, action: str, payload: dict[str, Any], prev_hash: str) -> str:
    """Deterministic serialization of a row's content for hashing."""
    return json.dumps(
        {"ts": ts, "actor": actor, "action": action, "payload": payload, "prev_hash": prev_hash},
        sort_keys=True,
        separators=(",", ":"),
    )


def _hash(canonical: str) -> str:
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def record(actor: str, action: str, payload: dict[str, Any], firm_id: str | None = None,
           ts: str | None = None) -> str:
    """Append an event to the audit chain. Returns the new row hash."""
    ts = ts or datetime.now(timezone.utc).isoformat()
    with connect() as conn:
        row = conn.execute("SELECT row_hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
        prev_hash = row["row_hash"] if row else GENESIS
        row_hash = _hash(_canonical(ts, actor, action, payload, prev_hash))
        conn.execute(
            "INSERT INTO audit_log (ts, firm_id, actor, action, payload, prev_hash, row_hash) VALUES (?,?,?,?,?,?,?)",
            (ts, firm_id, actor, action, json.dumps(payload), prev_hash, row_hash),
        )
    return row_hash


def get_log() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY seq").fetchall()
    return [dict(r) for r in rows]


def verify_chain() -> dict[str, Any]:
    """Recompute the entire chain; report the first row where it breaks, if any."""
    rows = get_log()
    prev = GENESIS
    for r in rows:
        expected_prev = prev
        recomputed = _hash(_canonical(r["ts"], r["actor"], r["action"], json.loads(r["payload"]), r["prev_hash"]))
        if r["prev_hash"] != expected_prev:
            return {"valid": False, "broken_at": r["seq"], "reason": "prev_hash mismatch (a row was inserted/removed/reordered)"}
        if recomputed != r["row_hash"]:
            return {"valid": False, "broken_at": r["seq"], "reason": "row content was altered after the fact"}
        prev = r["row_hash"]
    return {"valid": True, "rows": len(rows), "head": prev}


def demo_tamper() -> dict:
    """Self-contained demonstration: build a small chain, tamper one row, show it is detected.

    Operates on an in-memory chain so the real audit log is never touched.
    """
    events = [
        ("max-pipeline", "auto_approve", {"transaction_id": "t1", "code": "6300", "amount": 80.00}),
        ("demo-cpa", "approve", {"transaction_id": "t1"}),
        ("max-pipeline", "auto_approve", {"transaction_id": "t2", "code": "6010", "amount": 240.00}),
    ]
    chain, prev = [], GENESIS
    for actor, action, payload in events:
        ts = "2026-01-15T10:00:00+00:00"
        row_hash = _hash(_canonical(ts, actor, action, payload, prev))
        chain.append({"ts": ts, "actor": actor, "action": action, "payload": payload,
                      "prev_hash": prev, "row_hash": row_hash})
        prev = row_hash

    def verify(rows):
        p = GENESIS
        for i, r in enumerate(rows):
            rec = _hash(_canonical(r["ts"], r["actor"], r["action"], r["payload"], r["prev_hash"]))
            if r["prev_hash"] != p or rec != r["row_hash"]:
                return {"valid": False, "broken_at": i + 1}
            p = r["row_hash"]
        return {"valid": True, "rows": len(rows)}

    import copy
    tampered = copy.deepcopy(chain)
    tampered[0]["payload"]["amount"] = 8000.00  # someone edits a posted amount
    return {
        "scenario": "An employee edits a posted transaction amount (80.00 to 8000.00) to hide activity.",
        "clean": verify(chain),
        "tampered": {**verify(tampered), "edit": "row 1 amount 80.00 to 8000.00"},
        "solution": "Every event commits to the previous event's hash. Any edit breaks the chain and is detected immediately.",
    }


def export_csv() -> str:
    """Auditor-friendly CSV export of the full chain."""
    import csv
    import io

    rows = get_log()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["seq", "ts", "actor", "action", "payload", "prev_hash", "row_hash"])
    for r in rows:
        w.writerow([r["seq"], r["ts"], r["actor"], r["action"], r["payload"], r["prev_hash"], r["row_hash"]])
    return buf.getvalue()
