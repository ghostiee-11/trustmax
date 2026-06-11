"""Extraction agent: read a document and pull structured fields, each with provenance (the exact
span in the document it came from). This is what turns 'route a file' into 'understand a file' and
feeds both routing (sender, EIN, account) and data entry (vendor, date, amount).

The document body is rendered from the record (synthetic in this demo, real OCR text in production),
and every extracted field carries the character span it was found at, so a human can verify it.
"""
from __future__ import annotations

from .. import db


def build_body(doc: dict) -> str:
    vendor = doc.get("vendor_hint") or "Vendor"
    lines = [vendor, "", doc.get("doc_type", "document").replace("_", " ").title(),
             f"Date: {doc.get('doc_date', '')}"]
    if doc.get("ein_hint"):
        lines.append(f"Tax ID (EIN): {doc['ein_hint']}")
    if doc.get("account_last4"):
        lines.append(f"Account ending {doc['account_last4']}")
    amt = doc.get("amount")
    lines.append(f"Amount: ${amt:,.2f}" if amt is not None else "Amount: --")
    lines.append(f"Remit to: {vendor}")
    return "\n".join(lines)


def extract(doc: dict) -> dict:
    body = build_body(doc)
    fields = []

    def add(name: str, value) -> None:
        if value in (None, ""):
            return
        token = str(value)
        idx = body.find(token)
        fields.append({"name": name, "value": value,
                       "span": [idx, idx + len(token)] if idx >= 0 else None})

    add("vendor", doc.get("vendor_hint"))
    add("date", doc.get("doc_date"))
    if doc.get("amount") is not None:
        add("amount", f"{doc['amount']:,.2f}")
    add("ein", doc.get("ein_hint"))
    add("account_last4", doc.get("account_last4"))

    expected = 5
    return {
        "document_id": doc["id"], "doc_type": doc.get("doc_type"),
        "body": body, "fields": fields,
        "extracted": {f["name"]: f["value"] for f in fields},
        "confidence": round(len(fields) / expected, 2),
    }


def extract_by_id(firm_id: str, doc_id: str) -> dict:
    docs = {d["id"]: d for d in db.get_documents(firm_id)}
    doc = docs.get(doc_id)
    if not doc:
        return {"error": "document not found"}
    return extract(doc)
