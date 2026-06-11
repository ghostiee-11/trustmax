"""Relational persistence for Trustmax (multi-tenant).

Default backend is stdlib sqlite3 (zero setup). A Supabase/Postgres backend can be added behind the
same functions via DATABASE_URL without changing business logic. Every domain row is tenant-scoped by
`firm_id`; callers pass the firm and queries filter on it (enforced at the security layer too).
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS firms (
    id TEXT PRIMARY KEY, name TEXT, slug TEXT
);
CREATE TABLE IF NOT EXISTS employees (
    id TEXT PRIMARY KEY, firm_id TEXT, name TEXT, role TEXT, email TEXT
);
CREATE TABLE IF NOT EXISTS clients (
    id TEXT PRIMARY KEY, firm_id TEXT, name TEXT, industry TEXT,
    ein TEXT, email_domain TEXT, bank_last4 TEXT
);
CREATE TABLE IF NOT EXISTS engagements (
    id TEXT PRIMARY KEY, firm_id TEXT, client_id TEXT, type TEXT, period TEXT, status TEXT
);
CREATE TABLE IF NOT EXISTS gl_accounts (
    id TEXT PRIMARY KEY, firm_id TEXT, code TEXT, name TEXT, type TEXT, description TEXT
);
CREATE TABLE IF NOT EXISTS vendors (
    id TEXT PRIMARY KEY, firm_id TEXT, canonical_name TEXT, mcc TEXT, category TEXT, default_code TEXT
);
CREATE TABLE IF NOT EXISTS vendor_aliases (
    id TEXT PRIMARY KEY, firm_id TEXT, vendor_id TEXT, alias TEXT
);
CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY, firm_id TEXT, client_id TEXT, engagement_id TEXT, batch_id TEXT,
    date TEXT, vendor_raw TEXT, vendor_id TEXT, memo TEXT, amount REAL,
    source_doc_id TEXT, source_span TEXT, gt_code TEXT,
    is_anomaly INTEGER DEFAULT 0, anomaly_type TEXT
);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY, firm_id TEXT, doc_type TEXT, filename TEXT,
    sender_email TEXT, sender_domain TEXT, ein_hint TEXT, account_last4 TEXT, vendor_hint TEXT,
    gt_client_id TEXT, routed_client_id TEXT, routing_status TEXT, routing_confidence REAL,
    received_at TEXT
);
CREATE TABLE IF NOT EXISTS categorizations (
    transaction_id TEXT PRIMARY KEY, firm_id TEXT, batch_id TEXT, data TEXT
);
CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY, firm_id TEXT, transaction_id TEXT, type TEXT, severity TEXT,
    evidence TEXT, status TEXT
);
CREATE TABLE IF NOT EXISTS qa_pairs (
    id TEXT PRIMARY KEY, firm_id TEXT, client_id TEXT, question TEXT, kind TEXT, answer TEXT
);
CREATE TABLE IF NOT EXISTS audit_log (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, firm_id TEXT,
    actor TEXT, action TEXT, payload TEXT, prev_hash TEXT, row_hash TEXT
);
CREATE TABLE IF NOT EXISTS eval_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, suite TEXT, batch_id TEXT, metrics TEXT
);
CREATE INDEX IF NOT EXISTS ix_tx_firm ON transactions(firm_id);
CREATE INDEX IF NOT EXISTS ix_tx_client ON transactions(client_id);
CREATE INDEX IF NOT EXISTS ix_tx_batch ON transactions(batch_id);
CREATE INDEX IF NOT EXISTS ix_doc_firm ON documents(firm_id);
CREATE INDEX IF NOT EXISTS ix_alert_firm ON alerts(firm_id);
"""

_DOMAIN_TABLES = ["firms", "employees", "clients", "engagements", "gl_accounts", "vendors",
                  "vendor_aliases", "transactions", "documents", "categorizations", "alerts",
                  "qa_pairs", "audit_log", "eval_runs"]


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def reset_db() -> None:
    with connect() as conn:
        for t in _DOMAIN_TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {t}")
        conn.executescript(SCHEMA)


def insert_rows(table: str, rows: list[dict]) -> None:
    """Bulk insert. All rows must share keys."""
    if not rows:
        return
    cols = list(rows[0].keys())
    placeholders = ",".join("?" for _ in cols)
    sql = f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
    with connect() as conn:
        conn.executemany(sql, [[r.get(c) for c in cols] for r in rows])


def _rows(sql: str, params: tuple = ()) -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


# ---- domain getters (tenant-scoped) ------------------------------------------
def get_firms() -> list[dict]:
    return _rows("SELECT * FROM firms ORDER BY id")


def get_employees(firm_id: str) -> list[dict]:
    return _rows("SELECT * FROM employees WHERE firm_id=?", (firm_id,))


def get_clients(firm_id: str) -> list[dict]:
    return _rows("SELECT * FROM clients WHERE firm_id=? ORDER BY id", (firm_id,))


def get_engagements(firm_id: str, client_id: Optional[str] = None) -> list[dict]:
    if client_id:
        return _rows("SELECT * FROM engagements WHERE firm_id=? AND client_id=?", (firm_id, client_id))
    return _rows("SELECT * FROM engagements WHERE firm_id=?", (firm_id,))


def get_gl_accounts(firm_id: str) -> list[dict]:
    return _rows("SELECT * FROM gl_accounts WHERE firm_id=? ORDER BY code", (firm_id,))


def get_vendors(firm_id: str) -> list[dict]:
    return _rows("SELECT * FROM vendors WHERE firm_id=? ORDER BY canonical_name", (firm_id,))


def get_vendor_aliases(firm_id: str) -> list[dict]:
    return _rows("SELECT * FROM vendor_aliases WHERE firm_id=?", (firm_id,))


def get_transactions(firm_id: str, batch_id: Optional[str] = None,
                     client_id: Optional[str] = None) -> list[dict]:
    sql = "SELECT * FROM transactions WHERE firm_id=?"
    params: list[Any] = [firm_id]
    if batch_id:
        sql += " AND batch_id=?"; params.append(batch_id)
    if client_id:
        sql += " AND client_id=?"; params.append(client_id)
    sql += " ORDER BY date, id"
    return _rows(sql, tuple(params))


def get_transaction(transaction_id: str) -> Optional[dict]:
    rows = _rows("SELECT * FROM transactions WHERE id=?", (transaction_id,))
    return rows[0] if rows else None


def list_batches(firm_id: str) -> list[str]:
    rows = _rows("SELECT DISTINCT batch_id FROM transactions WHERE firm_id=? ORDER BY batch_id", (firm_id,))
    return [r["batch_id"] for r in rows]


def get_documents(firm_id: str, status: Optional[str] = None) -> list[dict]:
    if status:
        return _rows("SELECT * FROM documents WHERE firm_id=? AND routing_status=?", (firm_id, status))
    return _rows("SELECT * FROM documents WHERE firm_id=?", (firm_id,))


def update_document_routing(doc_id: str, routed_client_id: Optional[str],
                            status: str, confidence: float) -> None:
    with connect() as conn:
        conn.execute("UPDATE documents SET routed_client_id=?, routing_status=?, routing_confidence=? WHERE id=?",
                     (routed_client_id, status, confidence, doc_id))


# ---- categorizations ----------------------------------------------------------
def save_categorization(cat: dict) -> None:
    with connect() as conn:
        conn.execute("INSERT OR REPLACE INTO categorizations (transaction_id, firm_id, batch_id, data) VALUES (?,?,?,?)",
                     (cat["transaction_id"], cat.get("firm_id"), cat.get("batch_id"), json.dumps(cat)))


def get_categorization(transaction_id: str) -> Optional[dict]:
    rows = _rows("SELECT data FROM categorizations WHERE transaction_id=?", (transaction_id,))
    return json.loads(rows[0]["data"]) if rows else None


def get_categorizations(firm_id: str, batch_id: Optional[str] = None) -> list[dict]:
    if batch_id:
        rows = _rows("SELECT data FROM categorizations WHERE firm_id=? AND batch_id=?", (firm_id, batch_id))
    else:
        rows = _rows("SELECT data FROM categorizations WHERE firm_id=?", (firm_id,))
    return [json.loads(r["data"]) for r in rows]


# ---- alerts -------------------------------------------------------------------
def save_alert(alert: dict) -> None:
    with connect() as conn:
        conn.execute("INSERT OR REPLACE INTO alerts (id, firm_id, transaction_id, type, severity, evidence, status) VALUES (?,?,?,?,?,?,?)",
                     (alert["id"], alert["firm_id"], alert.get("transaction_id"), alert["type"],
                      alert["severity"], json.dumps(alert.get("evidence", {})), alert.get("status", "open")))


def get_alerts(firm_id: str) -> list[dict]:
    rows = _rows("SELECT * FROM alerts WHERE firm_id=? ORDER BY severity DESC", (firm_id,))
    for r in rows:
        r["evidence"] = json.loads(r["evidence"]) if r.get("evidence") else {}
    return rows


# ---- Q&A ----------------------------------------------------------------------
def get_qa_pairs(firm_id: str, client_id: Optional[str] = None) -> list[dict]:
    if client_id:
        rows = _rows("SELECT * FROM qa_pairs WHERE firm_id=? AND client_id=?", (firm_id, client_id))
    else:
        rows = _rows("SELECT * FROM qa_pairs WHERE firm_id=?", (firm_id,))
    for r in rows:
        r["answer"] = json.loads(r["answer"]) if r.get("answer") else {}
    return rows


# ---- evals --------------------------------------------------------------------
def save_eval_run(suite: str, batch_id: str, metrics: dict) -> None:
    with connect() as conn:
        conn.execute("INSERT INTO eval_runs (suite, batch_id, metrics) VALUES (?,?,?)",
                     (suite, batch_id, json.dumps(metrics)))


def get_eval_runs(suite: Optional[str] = None) -> list[dict]:
    if suite:
        rows = _rows("SELECT suite, batch_id, metrics FROM eval_runs WHERE suite=? ORDER BY id", (suite,))
    else:
        rows = _rows("SELECT suite, batch_id, metrics FROM eval_runs ORDER BY id")
    return [{"suite": r["suite"], "batch_id": r["batch_id"], **json.loads(r["metrics"])} for r in rows]
