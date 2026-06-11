"""Live ingest: take fresh input (a pasted bank feed or a document) and run the autonomous pipeline,
watching the knowledge graph grow in real time.

This is the "drop something in and the system just handles it" moment. A user pastes new bank lines or
an invoice, and Trustmax resolves the vendors on the graph, codes each item against the chart plus the
learned facts, flags anything odd, and writes the new transactions, edges, and learned facts straight
into the knowledge graph. We snapshot the graph before and after so the growth is visible: this is the
flywheel turning on live input, not a batch job.
"""
from __future__ import annotations

import csv
import io
import re

from .. import db
from ..kg.store import get_store
from ..trust import audit
from . import code_agent
from .extract_agent import extract
from .router_agent import RouterAgent

SAMPLE_FEED = """date,description,amount
2026-03-02,AWS EMEA,842.10
2026-03-04,NOTION LABS INC,16.00
2026-03-06,UPWORK *FREELANCE,1450.00
2026-03-09,GOOGLE *ADS,1320.55
2026-03-12,DELTA AIR,612.40
2026-03-15,STRIPE FEE,42.18
2026-03-18,Brightline Logistics LLC,2310.00
"""

SAMPLE_INVOICE = """Apex Supplies Co

Invoice
Date: 2026-03-14
Tax ID (EIN): 47-2213399
Account ending 4021
Amount: $1,840.00
Remit to: Apex Supplies Co
"""


def _snapshot() -> dict:
    try:
        s = get_store().stats()
        return {"nodes": int(s.get("nodes", 0)), "edges": int(s.get("edges", 0)),
                "facts": int(s.get("open_coded_to", 0))}
    except Exception:
        return {"nodes": 0, "edges": 0, "facts": 0}


def _parse_feed(text: str) -> list[tuple[str, str, str]]:
    """Return (date, description, amount) rows from CSV or freeform lines."""
    text = (text or "").strip()
    if not text:
        return []
    # CSV with an amount column
    try:
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames and any("amount" in (f or "").lower() for f in reader.fieldnames):
            out = []
            for r in reader:
                g = {(k or "").lower().strip(): v for k, v in r.items()}
                out.append((g.get("date", ""), g.get("description") or g.get("vendor") or g.get("memo") or "",
                            g.get("amount", "0")))
            return out
    except Exception:
        pass
    # freeform: optional leading date, a description, and a trailing amount
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.search(r"(-?\$?\d[\d,]*\.?\d{0,2})\s*$", line)
        amount = m.group(1) if m else "0"
        desc = line[: m.start()].strip(" ,\t") if m else line
        date = ""
        dm = re.match(r"(\d{4}-\d{2}-\d{2})[ ,\t]+(.*)", desc)
        if dm:
            date, desc = dm.group(1), dm.group(2).strip()
        out.append((date, desc, amount))
    return out


def _to_amount(raw: str) -> float:
    try:
        return round(float(str(raw).replace("$", "").replace(",", "").strip() or 0), 2)
    except ValueError:
        return 0.0


def _write_to_graph(store, firm_id: str, tx: dict, cat: dict) -> int:
    """Write a coded transaction into the graph. Returns 1 if a new learned fact was created."""
    store.add_node("Transaction", firm_id, tx["id"], {
        "date": tx["date"], "vendor_raw": tx["vendor_raw"], "amount": tx["amount"],
        "client_id": tx["client_id"], "batch_id": tx["batch_id"]})
    store.add_edge("FOR_CLIENT", firm_id, "Transaction", tx["id"], "Client", tx["client_id"])
    learned = 0
    vid = cat.get("vendor_id")
    if vid:
        store.add_edge("REFERENCES", firm_id, "Transaction", tx["id"], "Vendor", vid)
        # the system approved this coding within policy, so it reinforces the graph (the flywheel)
        if cat.get("status") == "auto_approved" and cat.get("predicted_code"):
            before = store.get_current_code(firm_id, vid, tx["client_id"])
            store.set_coded_to(firm_id, vid, tx["client_id"], cat["predicted_code"],
                               float(cat.get("calibrated_confidence") or 0.9), "ingest:auto")
            after = store.get_current_code(firm_id, vid, tx["client_id"])
            if not before or before.get("code") != (after or {}).get("code"):
                learned = 1
    return learned


def _eng_id(firm_id: str, client_id: str) -> str:
    engs = db.get_engagements(firm_id, client_id)
    return engs[0]["id"] if engs else f"{client_id}-e0"


def ingest_feed(firm_id: str, client_id: str, text: str) -> dict:
    rows = _parse_feed(text)
    if not rows:
        return {"error": "Nothing to ingest. Paste a few bank lines or a CSV."}

    before = _snapshot()
    eng_id = _eng_id(firm_id, client_id)
    txns = []
    for i, (date, desc, amt) in enumerate(rows):
        txns.append({"id": f"{client_id}-live-{i}", "firm_id": firm_id, "client_id": client_id,
                     "engagement_id": eng_id, "batch_id": "live", "date": date or "2026-03-01",
                     "vendor_raw": desc or "Unknown", "vendor_id": None, "memo": "live ingest",
                     "amount": _to_amount(amt), "source_doc_id": "live_feed",
                     "source_span": f"feed row {i + 1}", "gt_code": None,
                     "is_anomaly": 0, "anomaly_type": None})
    db.insert_rows("transactions", txns)

    store = get_store()
    accounts = db.get_gl_accounts(firm_id)
    compiled, meta = code_agent.build_pipeline(firm_id, txns, accounts)
    items, learned, matched, auto = [], 0, 0, 0
    for tx in txns:
        cat = code_agent.categorize_one(compiled, meta, firm_id, "live", tx)
        learned += _write_to_graph(store, firm_id, tx, cat)
        if cat.get("vendor_id"):
            matched += 1
        if cat.get("status") == "auto_approved":
            auto += 1
        items.append({
            "vendor": tx["vendor_raw"], "amount": tx["amount"], "code": cat.get("predicted_code"),
            "account": cat.get("predicted_account_name"), "confidence": cat.get("calibrated_confidence"),
            "status": cat.get("status"), "grounded": (cat.get("graph_support") or 0) > 0,
            "flags": cat.get("anomaly_flags") or [], "reasoning_path": cat.get("reasoning_path") or []})

    if hasattr(store, "save"):
        store.save()
    after = _snapshot()
    audit.record("max-ingest", "live_ingest",
                 {"client_id": client_id, "rows": len(txns), "facts_learned": learned}, firm_id=firm_id)

    n = len(txns)
    return {
        "kind": "feed", "before": before, "after": after,
        "delta": {"nodes": after["nodes"] - before["nodes"], "edges": after["edges"] - before["edges"],
                  "facts": after["facts"] - before["facts"]},
        "counts": {"ingested": n, "auto_approved": auto, "needs_review": n - auto,
                   "vendors_resolved": matched, "facts_learned": learned},
        "trace": [
            {"label": "Parsed the input", "detail": f"{n} lines", "ok": True},
            {"label": "Resolved vendors on the graph", "detail": f"{matched} of {n} linked to a known vendor", "ok": True},
            {"label": "Coded against the chart and learned facts", "detail": f"{auto} auto-approved, {n - auto} to review", "ok": True},
            {"label": "Wrote new nodes and edges to the graph", "detail": f"+{after['nodes'] - before['nodes']} nodes, +{after['edges'] - before['edges']} edges", "ok": True},
            {"label": "Reinforced the graph with learned facts", "detail": f"+{learned} vendor to account facts", "ok": True},
        ],
        "items": items,
    }


def _parse_invoice(text: str) -> dict:
    text = text or ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    vendor = ""
    mremit = re.search(r"(?:remit to|bill from|from|vendor)\s*:?\s*(.+)", text, re.IGNORECASE)
    if mremit:
        vendor = mremit.group(1).strip()
    elif lines:
        vendor = lines[0]
    mamt = re.search(r"(?:amount|total|amount due)\s*:?\s*\$?\s*([\d,]+\.?\d{0,2})", text, re.IGNORECASE)
    if not mamt:
        mamt = re.search(r"\$\s*([\d,]+\.\d{2})", text)
    amount = _to_amount(mamt.group(1)) if mamt else 0.0
    mdate = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    date = mdate.group(1) if mdate else "2026-03-01"
    mein = re.search(r"(\d{2}-\d{7})", text)
    macct = re.search(r"ending\s*(\d{4})", text, re.IGNORECASE)
    memail = re.search(r"[\w.+-]+@([\w.-]+)", text)
    return {"vendor": vendor, "amount": amount, "date": date,
            "ein": mein.group(1) if mein else None,
            "account_last4": macct.group(1) if macct else None,
            "domain": memail.group(1) if memail else None}


def ingest_document(firm_id: str, client_id: str, text: str, filename: str = "pasted_invoice.pdf") -> dict:
    parsed = _parse_invoice(text)
    if not parsed["vendor"] and parsed["amount"] == 0:
        return {"error": "Could not read a vendor or amount from that document."}

    before = _snapshot()
    doc_id = f"{client_id}-livedoc"
    doc = {"id": doc_id, "firm_id": firm_id, "doc_type": "invoice", "filename": filename,
           "sender_email": None, "sender_domain": parsed["domain"], "ein_hint": parsed["ein"],
           "account_last4": parsed["account_last4"], "vendor_hint": parsed["vendor"],
           "amount": parsed["amount"], "doc_date": parsed["date"], "gt_client_id": client_id,
           "routed_client_id": None, "routing_status": "pending", "routing_confidence": None,
           "received_at": parsed["date"]}
    db.insert_rows("documents", [doc])

    # route to the right client on the graph; only trust an auto-route at near-certain confidence,
    # otherwise keep it on the human-selected client (you approve everything)
    from ..config import AUTO_ROUTE_THRESHOLD
    agent = RouterAgent(firm_id)
    routed = agent.route(doc)
    cmap = {c["id"]: c["name"] for c in db.get_clients(firm_id)}
    auto = routed.get("client_id") is not None and (routed.get("confidence") or 0) >= AUTO_ROUTE_THRESHOLD
    target = routed["client_id"] if auto else client_id

    store = get_store()
    store.add_node("Document", firm_id, doc_id, {"doc_type": "invoice", "filename": filename,
                                                 "sender_domain": parsed["domain"], "received_at": parsed["date"]})
    store.add_edge("BELONGS_TO", firm_id, "Document", doc_id, "Client", target)

    # extract structured fields with provenance
    extracted = extract(doc)

    # create and code the transaction the document implies
    eng_id = _eng_id(firm_id, target)
    tx = {"id": f"{doc_id}-tx", "firm_id": firm_id, "client_id": target, "engagement_id": eng_id,
          "batch_id": "live", "date": parsed["date"], "vendor_raw": parsed["vendor"] or "Vendor",
          "vendor_id": None, "memo": "from ingested document", "amount": parsed["amount"],
          "source_doc_id": doc_id, "source_span": "document body", "gt_code": None,
          "is_anomaly": 0, "anomaly_type": None}
    db.insert_rows("transactions", [tx])
    accounts = db.get_gl_accounts(firm_id)
    compiled, meta = code_agent.build_pipeline(firm_id, [tx], accounts)
    cat = code_agent.categorize_one(compiled, meta, firm_id, "live", tx)
    learned = _write_to_graph(store, firm_id, tx, cat)

    if hasattr(store, "save"):
        store.save()
    after = _snapshot()
    audit.record("max-ingest", "document_ingest",
                 {"client_id": target, "document": doc_id, "facts_learned": learned}, firm_id=firm_id)

    return {
        "kind": "document", "before": before, "after": after,
        "delta": {"nodes": after["nodes"] - before["nodes"], "edges": after["edges"] - before["edges"],
                  "facts": after["facts"] - before["facts"]},
        "routing": {"client_id": target, "client_name": cmap.get(target), "confidence": routed.get("confidence"),
                    "auto": auto, "evidence": routed.get("evidence", [])},
        "fields": extracted.get("fields", []),
        "coded": {"vendor": tx["vendor_raw"], "amount": tx["amount"], "code": cat.get("predicted_code"),
                  "account": cat.get("predicted_account_name"), "confidence": cat.get("calibrated_confidence"),
                  "status": cat.get("status"), "grounded": (cat.get("graph_support") or 0) > 0,
                  "reasoning_path": cat.get("reasoning_path") or []},
        "trace": [
            {"label": "Read the document", "detail": f"{len(extracted.get('fields', []))} fields extracted with provenance", "ok": True},
            {"label": ("Auto-routed to the right client" if auto else "Routing unsure, kept on the selected client"),
             "detail": (f"{cmap.get(target)} at {round((routed.get('confidence') or 0) * 100)}% confidence"
                        if auto else f"{cmap.get(target)} (a human confirms before posting)"), "ok": True},
            {"label": "Coded the implied transaction", "detail": f"{cat.get('predicted_code')} {cat.get('predicted_account_name')} ({cat.get('status')})", "ok": True},
            {"label": "Wrote to the knowledge graph", "detail": f"+{after['nodes'] - before['nodes']} nodes, +{after['edges'] - before['edges']} edges, +{learned} facts", "ok": True},
        ],
    }


def ingest(firm_id: str, client_id: str, kind: str, text: str, filename: str = "") -> dict:
    if kind == "document":
        return ingest_document(firm_id, client_id, text, filename or "pasted_invoice.pdf")
    return ingest_feed(firm_id, client_id, text)
