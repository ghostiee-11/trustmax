"""Proactive Ed: the document-collection agent.

The #1 pain in a CPA firm is chasing missing documents and following up on clients. This agent keeps a
PBC ("provided by client") checklist per engagement, detects what is still missing, and drafts a warm,
approval-gated reminder to the client. Nothing is sent without the firm's approval.
"""
from __future__ import annotations

from .. import db
from ..providers import get_provider
from ..trust import audit

REQUIRED = {
    "Bookkeeping": ["bank_statement", "receipt", "invoice"],
    "Tax": ["bank_statement", "tax_form", "prior_return", "receipt"],
    "Audit": ["bank_statement", "engagement_letter", "invoice", "prior_return"],
}
LABEL = {
    "bank_statement": "bank statements", "receipt": "receipts", "invoice": "vendor invoices",
    "tax_form": "tax forms (W-2s / 1099s)", "prior_return": "last year's tax return",
    "engagement_letter": "the signed engagement letter",
}


def pbc_status(firm_id: str, client_id: str) -> dict:
    engs = db.get_engagements(firm_id, client_id)
    etype = engs[0]["type"] if engs else "Tax"
    required = REQUIRED.get(etype, REQUIRED["Tax"])
    received = {d["doc_type"] for d in db.get_documents(firm_id) if d["gt_client_id"] == client_id}
    missing = [r for r in required if r not in received]
    cname = next((c["name"] for c in db.get_clients(firm_id) if c["id"] == client_id), client_id)
    return {"client_id": client_id, "client": cname, "engagement_type": etype,
            "required": required, "received": [r for r in required if r in received],
            "missing": missing, "complete": not missing}


def firm_pbc(firm_id: str) -> dict:
    rows = [pbc_status(firm_id, c["id"]) for c in db.get_clients(firm_id)]
    incomplete = [r for r in rows if not r["complete"]]
    return {"firm_id": firm_id, "clients": rows,
            "summary": {"total": len(rows), "complete": len(rows) - len(incomplete),
                        "waiting_on_docs": len(incomplete)}}


def draft_reminder(firm_id: str, client_id: str) -> dict:
    st = pbc_status(firm_id, client_id)
    if st["complete"]:
        return {"client_id": client_id, "complete": True, "message": None}
    items = [LABEL.get(m, m) for m in st["missing"]]
    items_text = ", ".join(items[:-1]) + (" and " + items[-1] if len(items) > 1 else items[0])
    template = (f"Hi {st['client']}, we're getting your books in order and are just waiting on a few items: "
                f"{items_text}. Whenever you have a moment, you can upload them to your portal. Thanks so much.")

    provider = get_provider()
    body = template
    if provider.name == "groq":
        try:
            sys = ("You are Ed, a warm CPA-firm assistant writing a short reminder to a client about "
                   "missing documents. Mention exactly the items given, keep it under 70 words, friendly, "
                   "no em dashes, and do not invent anything.")
            out = provider.chat(sys, f"Client: {st['client']}\nMissing items: {items_text}").strip()
            body = (out or template).replace("—", ", ").replace("–", ", ")
        except Exception:
            body = template

    msg = {"id": f"pbc-{client_id}", "client_id": client_id, "missing": st["missing"],
           "subject": "A couple of documents we still need", "body": body, "status": "pending_approval"}
    audit.record("ed-collection", "draft_reminder",
                 {"client_id": client_id, "missing": st["missing"]}, firm_id=firm_id)
    return msg
