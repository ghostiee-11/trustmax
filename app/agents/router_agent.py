"""Route agent: link each incoming document to the correct client (Maxed's "route to the right file").

Misrouting a document to the wrong client is a confidentiality breach, so the policy is deliberately
conservative: combine high-precision deterministic keys (EIN, email domain, bank account last-4) with
a graph signal (which clients actually transact with the document's vendor), and only auto-route above
a high confidence bar. Everything else goes to a human "which client?" queue. Every routing is written
to the graph (Document)-[:BELONGS_TO]->(Client) and to the tamper-evident audit log.
"""
from __future__ import annotations

from collections import defaultdict

from .. import config, db
from ..kg.store import get_store
from ..trust import audit


class RouterAgent:
    def __init__(self, firm_id: str):
        self.firm_id = firm_id
        clients = db.get_clients(firm_id)
        self.clients = clients
        self.by_ein = {c["ein"]: c["id"] for c in clients if c.get("ein")}
        self.by_domain = {c["email_domain"]: c["id"] for c in clients if c.get("email_domain")}
        self.last4_index: dict[str, list[str]] = defaultdict(list)
        for c in clients:
            if c.get("bank_last4"):
                self.last4_index[c["bank_last4"]].append(c["id"])
        # graph signal: which clients transact with each vendor (by canonical name)
        vid_to_name = {v["id"]: v["canonical_name"] for v in db.get_vendors(firm_id)}
        self.vendor_clients: dict[str, set] = defaultdict(set)
        for t in db.get_transactions(firm_id):
            name = vid_to_name.get(t.get("vendor_id"))
            if name:
                self.vendor_clients[name].add(t["client_id"])

    def route(self, doc: dict) -> dict:
        scores: dict[str, float] = defaultdict(float)
        evidence: dict[str, list] = defaultdict(list)

        # EIN is a globally-unique identifier: a match is essentially definitive.
        if doc.get("ein_hint") and doc["ein_hint"] in self.by_ein:
            cid = self.by_ein[doc["ein_hint"]]
            scores[cid] += 0.95
            evidence[cid].append(f"EIN {doc['ein_hint']} matches client")
        # Each client's email domain is unique here: a match is a strong, safe signal.
        if doc.get("sender_domain") and doc["sender_domain"] in self.by_domain:
            cid = self.by_domain[doc["sender_domain"]]
            scores[cid] += 0.90
            evidence[cid].append(f"sender domain {doc['sender_domain']} matches client")
        # Bank last-4 can collide, so it corroborates but does not auto-route on its own.
        if doc.get("account_last4"):
            matches = self.last4_index.get(doc["account_last4"], [])
            if len(matches) == 1:
                scores[matches[0]] += 0.35
                evidence[matches[0]].append(f"bank account ...{doc['account_last4']} matches")
            elif len(matches) > 1:
                for cid in matches:
                    scores[cid] += 0.05  # ambiguous, weak
        if doc.get("vendor_hint"):
            for cid in self.vendor_clients.get(doc["vendor_hint"], set()):
                scores[cid] += 0.08
                evidence[cid].append(f"client transacts with {doc['vendor_hint']}")

        if not scores:
            return {"client_id": None, "confidence": 0.0, "method": "abstain", "evidence": []}

        best = max(scores, key=scores.get)
        conf = min(0.99, scores[best])
        # margin check: if the runner-up is close, drop confidence (ambiguous -> human)
        ordered = sorted(scores.values(), reverse=True)
        if len(ordered) > 1 and (ordered[0] - ordered[1]) < 0.1:
            conf = min(conf, 0.6)
        return {"client_id": best, "confidence": round(conf, 3),
                "method": "deterministic+graph", "evidence": evidence[best]}

    def process(self, doc: dict) -> dict:
        res = self.route(doc)
        threshold = config.AUTO_ROUTE_THRESHOLD
        auto = res["client_id"] is not None and res["confidence"] >= threshold
        status = "auto_routed" if auto else "needs_review"
        db.update_document_routing(doc["id"], res["client_id"] if auto else None,
                                   status, res["confidence"])
        if auto:
            get_store().add_edge("BELONGS_TO", self.firm_id, "Document", doc["id"],
                                 "Client", res["client_id"],
                                 {"confidence": res["confidence"], "method": res["method"]})
        audit.record("route-agent", status, {
            "document_id": doc["id"], "routed_client_id": res["client_id"] if auto else None,
            "confidence": res["confidence"]}, firm_id=self.firm_id)
        return {**res, "status": status, "document_id": doc["id"]}


def run_firm(firm_id: str) -> dict:
    agent = RouterAgent(firm_id)
    docs = db.get_documents(firm_id)
    results = [agent.process(d) for d in docs]
    auto = sum(1 for r in results if r["status"] == "auto_routed")
    return {"firm_id": firm_id, "documents": len(docs), "auto_routed": auto,
            "needs_review": len(docs) - auto}
