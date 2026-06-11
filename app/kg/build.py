"""Ingest the relational corpus into the knowledge graph.

Builds the structural graph (firms, clients, engagements, vendors, GL accounts, transactions,
documents, employees + structural edges). It deliberately does NOT seed `CODED_TO` facts or
`Document -> Client` links: the coding facts are *learned* from human approvals (the flywheel), and
document->client links are *predicted* by the routing agent. So the graph reflects only what is known
up front, and trust is earned over time.

Run: `python -m app.kg.build`
"""
from __future__ import annotations

import json

from .. import db
from .store import get_store, reset_store


def build(reset: bool = True) -> dict:
    store = get_store()
    if reset:
        store.reset()

    firms = db.get_firms()
    for firm in firms:
        fid = firm["id"]
        store.add_node("Firm", fid, fid, {"name": firm["name"], "slug": firm["slug"]})

        store.add_nodes("Employee", fid, [
            (e["id"], {"name": e["name"], "role": e["role"], "email": e["email"]})
            for e in db.get_employees(fid)])

        clients = db.get_clients(fid)
        store.add_nodes("Client", fid, [
            (c["id"], {"name": c["name"], "industry": c["industry"], "ein": c["ein"],
                       "email_domain": c["email_domain"], "bank_last4": c["bank_last4"]})
            for c in clients])
        store.add_edges("HAS_CLIENT", fid, [("Firm", fid, "Client", c["id"], {}) for c in clients])

        engs = db.get_engagements(fid)
        store.add_nodes("Engagement", fid, [
            (e["id"], {"type": e["type"], "period": e["period"], "status": e["status"]}) for e in engs])
        store.add_edges("HAS_ENGAGEMENT", fid,
                        [("Client", e["client_id"], "Engagement", e["id"], {}) for e in engs])

        store.add_nodes("GLAccount", fid, [
            (a["code"], {"name": a["name"], "type": a["type"], "description": a["description"]})
            for a in db.get_gl_accounts(fid)])

        # vendors with their aliases as a property array (entity-resolution input)
        aliases_by_vendor: dict[str, list[str]] = {}
        for a in db.get_vendor_aliases(fid):
            aliases_by_vendor.setdefault(a["vendor_id"], []).append(a["alias"])
        vendors = db.get_vendors(fid)
        store.add_nodes("Vendor", fid, [
            (v["id"], {"canonical_name": v["canonical_name"], "category": v["category"],
                       "mcc": v["mcc"], "default_code": v["default_code"],
                       "aliases": aliases_by_vendor.get(v["id"], [])}) for v in vendors])

        txns = db.get_transactions(fid)
        store.add_nodes("Transaction", fid, [
            (t["id"], {"date": t["date"], "vendor_raw": t["vendor_raw"], "amount": t["amount"],
                       "client_id": t["client_id"], "batch_id": t["batch_id"]}) for t in txns])
        store.add_edges("FOR_CLIENT", fid,
                        [("Transaction", t["id"], "Client", t["client_id"], {}) for t in txns])
        store.add_edges("REFERENCES", fid,
                        [("Transaction", t["id"], "Vendor", t["vendor_id"], {})
                         for t in txns if t.get("vendor_id")])

        store.add_nodes("Document", fid, [
            (d["id"], {"doc_type": d["doc_type"], "filename": d["filename"],
                       "sender_domain": d["sender_domain"], "received_at": d["received_at"]})
            for d in db.get_documents(fid)])

    if store.backend == "networkx":
        store.save()
    stats = store.stats()
    return stats


def main() -> None:
    stats = build(reset=True)
    print("Knowledge graph built:")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
