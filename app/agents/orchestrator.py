"""Close orchestrator: the top-level Max workflow.

Given a client and period, it composes the agents into the actual CPA close: collect documents, route
what came in, extract fields, code the transactions, flag anomalies, and draft a client update, with a
human-approval gate at every client-facing or risky step. This is what turns a set of features into a
workflow a firm would actually run.
"""
from __future__ import annotations

from typing import Optional

from .. import db
from ..providers import get_provider
from ..trust import audit
from . import collection_agent, extract_agent
from .anomaly_agent import detect
from .router_agent import RouterAgent


def run_close(firm_id: str, client_id: str, period: Optional[str] = None) -> dict:
    steps = []
    cname = next((c["name"] for c in db.get_clients(firm_id) if c["id"] == client_id), client_id)

    # 1) collect documents (proactive Ed)
    pbc = collection_agent.pbc_status(firm_id, client_id)
    reminder = None if pbc["complete"] else collection_agent.draft_reminder(firm_id, client_id)
    steps.append({"step": "Collect documents", "status": "done" if pbc["complete"] else "waiting_on_client",
                  "detail": f"{len(pbc['received'])}/{len(pbc['required'])} received"
                            + ("" if pbc["complete"] else f", chasing {len(pbc['missing'])}"),
                  "data": {"pbc": pbc, "reminder": reminder}})

    # 2) route incoming documents to this client
    client_docs = [d for d in db.get_documents(firm_id) if d["gt_client_id"] == client_id]
    agent = RouterAgent(firm_id)
    routed = [agent.route(d) for d in client_docs]
    auto = sum(1 for r in routed if r["client_id"] and r["confidence"] >= 0.9)
    steps.append({"step": "Route documents", "status": "done",
                  "detail": f"{auto}/{len(client_docs)} auto-filed, rest to review",
                  "data": {"documents": len(client_docs), "auto_filed": auto}})

    # 3) extract fields from received documents
    extracts = [extract_agent.extract(d) for d in client_docs[:8]]
    n_fields = sum(len(e["fields"]) for e in extracts)
    steps.append({"step": "Extract data", "status": "done",
                  "detail": f"{n_fields} fields extracted from {len(extracts)} documents, with provenance",
                  "data": {"sample": extracts[:3]}})

    # 4) code the transactions
    cats = [c for c in db.get_categorizations(firm_id, period) if c.get("client_id") == client_id]
    coded_auto = sum(1 for c in cats if c.get("status") == "auto_approved")
    code_status = "done" if cats else "pending"
    steps.append({"step": "Code transactions", "status": code_status,
                  "detail": (f"{len(cats)} coded, {coded_auto} auto-approved" if cats else "not yet categorized"),
                  "data": {"coded": len(cats), "auto_approved": coded_auto}})

    # 5) flag anomalies
    alerts = [a for a in detect(firm_id, client_id)]
    steps.append({"step": "Flag anomalies", "status": "needs_review" if alerts else "done",
                  "detail": f"{len(alerts)} anomalies to review" if alerts else "no anomalies",
                  "data": {"alerts": alerts[:5]}})

    # 6) draft the client update (approval-gated)
    update = _draft_update(firm_id, cname, pbc, len(cats), coded_auto, len(alerts))
    steps.append({"step": "Draft client update", "status": "needs_approval",
                  "detail": "ready for your approval before sending",
                  "data": {"message": update}})

    done = sum(1 for s in steps if s["status"] == "done")
    audit.record("max-orchestrator", "run_close",
                 {"client_id": client_id, "period": period, "steps_done": done}, firm_id=firm_id)
    return {"firm_id": firm_id, "client_id": client_id, "client": cname, "period": period,
            "steps": steps, "summary": {"steps": len(steps), "done": done,
                                        "gates": sum(1 for s in steps if "needs" in s["status"] or "waiting" in s["status"])}}


def _draft_update(firm_id, cname, pbc, coded, auto, alerts) -> dict:
    missing = pbc["missing"]
    template = (f"Hi {cname}, quick update on your books. We've received {len(pbc['received'])} of "
                f"{len(pbc['required'])} document types and coded {coded} transactions ({auto} automatically). "
                + (f"We flagged {alerts} items to review with you. " if alerts else "")
                + ("We're just waiting on a few documents to finish up. " if missing else "Everything is in and we're wrapping up. ")
                + "Let us know if you have questions.")
    provider = get_provider()
    body = template
    if provider.name == "groq":
        try:
            sys = ("You are Ed, a warm CPA-firm assistant writing a short status update to a client. Use "
                   "ONLY the facts given, keep it under 80 words, friendly, no em dashes, invent nothing.")
            u = f"Client: {cname}\nDocs received: {len(pbc['received'])}/{len(pbc['required'])}\nCoded: {coded} ({auto} auto)\nFlagged: {alerts}\nStill missing: {missing}"
            body = (provider.chat(sys, u).strip() or template).replace("—", ", ").replace("–", ", ")
        except Exception:
            body = template
    return {"subject": "An update on your books", "body": body, "status": "pending_approval"}
