"""Trustmax HTTP API (FastAPI). The product surface the dashboard consumes.

Run: `uvicorn app.api:app --reload --port 8000`
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from . import db
from .agents.anomaly_agent import detect, run_firm as flag_firm
from .agents.answer_agent import AnswerAgent
from .agents.router_agent import RouterAgent
from .kg import lineage
from .kg.store import get_store
from .security import crypto, rbac
from .trust import audit

app = FastAPI(title="Trustmax", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class AskBody(BaseModel):
    firm_id: str
    client_id: str
    question: str
    context: dict | None = None
    history: list | None = None


class CloseBody(BaseModel):
    firm_id: str
    client_id: str
    period: str | None = None


class ImportBody(BaseModel):
    firm_id: str
    client_id: str
    csv: str


class IngestBody(BaseModel):
    firm_id: str
    client_id: str
    kind: str = "feed"
    text: str
    filename: str | None = None


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/meta")
def meta():
    from .providers import get_provider
    p = get_provider()
    return {"provider": p.name, "model": p.model or "n/a", "live": p.name != "mock"}


@app.get("/stats")
def stats():
    firms = db.get_firms()
    total_clients = sum(len(db.get_clients(f["id"])) for f in firms)
    with db.connect() as c:
        txns = c.execute("SELECT COUNT(*) AS n FROM transactions").fetchone()["n"]
        docs = c.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]
    try:
        kg = get_store().stats()
    except Exception:
        kg = {}
    return {"firms": len(firms), "clients": total_clients, "transactions": txns,
            "documents": docs, "knowledge_graph": kg}


@app.get("/firms")
def firms():
    return db.get_firms()


@app.get("/firms/{firm_id}/clients")
def clients(firm_id: str):
    return db.get_clients(firm_id)


@app.get("/firms/{firm_id}/overview")
def overview(firm_id: str):
    cls = db.get_clients(firm_id)
    txns = db.get_transactions(firm_id)
    docs = db.get_documents(firm_id)
    cats = db.get_categorizations(firm_id)
    auto = sum(1 for c in cats if c.get("status") == "auto_approved")
    return {
        "firm": next((f for f in db.get_firms() if f["id"] == firm_id), None),
        "clients": len(cls), "transactions": len(txns), "documents": len(docs),
        "categorized": len(cats), "auto_approved": auto,
        "pending_docs": sum(1 for d in docs if d["routing_status"] == "pending"),
    }


@app.get("/firms/{firm_id}/transactions")
def transactions(firm_id: str, client_id: str | None = None, batch_id: str | None = None, limit: int = 200):
    rows = db.get_transactions(firm_id, batch_id=batch_id, client_id=client_id)[:limit]
    out = []
    for t in rows:
        cat = db.get_categorization(t["id"]) or {}
        out.append({**t, "predicted_code": cat.get("predicted_code"),
                    "predicted_account_name": cat.get("predicted_account_name"),
                    "status": cat.get("status"), "calibrated_confidence": cat.get("calibrated_confidence"),
                    "graph_support": cat.get("graph_support"), "er_method": cat.get("er_method"),
                    "anomaly_flags": cat.get("anomaly_flags"), "reasoning_path": cat.get("reasoning_path")})
    return out


@app.get("/firms/{firm_id}/routing")
def routing(firm_id: str, limit: int = 60):
    from .config import AUTO_ROUTE_THRESHOLD
    agent = RouterAgent(firm_id)
    cmap = {c["id"]: c["name"] for c in db.get_clients(firm_id)}
    out = []
    for d in db.get_documents(firm_id)[:limit]:
        r = agent.route(d)
        auto = r["client_id"] is not None and r["confidence"] >= AUTO_ROUTE_THRESHOLD
        out.append({"id": d["id"], "filename": d["filename"], "doc_type": d["doc_type"],
                    "sender_domain": d["sender_domain"], "confidence": r["confidence"],
                    "routed_client": r["client_id"], "routed_client_name": cmap.get(r["client_id"]),
                    "status": "auto_routed" if auto else "needs_review", "evidence": r["evidence"]})
    return out


@app.get("/firms/{firm_id}/alerts")
def alerts(firm_id: str):
    persisted = db.get_alerts(firm_id)
    if persisted:
        return persisted
    return detect(firm_id)[:500]


@app.post("/firms/{firm_id}/flag/run")
def flag_run(firm_id: str):
    return flag_firm(firm_id)


@app.get("/firms/{firm_id}/documents")
def documents(firm_id: str, status: str | None = None):
    return db.get_documents(firm_id, status=status)[:500]


@app.post("/firms/{firm_id}/route/run")
def route_run(firm_id: str):
    agent = RouterAgent(firm_id)
    docs = db.get_documents(firm_id)
    results = [agent.process(d) for d in docs]
    auto = sum(1 for r in results if r["status"] == "auto_routed")
    return {"documents": len(docs), "auto_routed": auto, "needs_review": len(docs) - auto}


@app.post("/ask")
def ask(body: AskBody):
    return AnswerAgent(body.firm_id).answer(body.client_id, body.question,
                                            context=body.context, history=body.history)


@app.get("/firms/{firm_id}/documents/{doc_id}/extract")
def document_extract(firm_id: str, doc_id: str):
    from .agents.extract_agent import extract_by_id
    res = extract_by_id(firm_id, doc_id)
    if res.get("error"):
        raise HTTPException(404, res["error"])
    return res


@app.get("/firms/{firm_id}/pbc")
def pbc(firm_id: str):
    from .agents.collection_agent import firm_pbc
    return firm_pbc(firm_id)


@app.get("/firms/{firm_id}/pbc/{client_id}/reminder")
def pbc_reminder(firm_id: str, client_id: str):
    from .agents.collection_agent import draft_reminder
    return draft_reminder(firm_id, client_id)


@app.post("/close")
def close(body: CloseBody):
    from .agents.orchestrator import run_close
    return run_close(body.firm_id, body.client_id, body.period)


@app.get("/import/sample")
def import_sample():
    from .agents.importer import SAMPLE_CSV
    return {"csv": SAMPLE_CSV}


@app.post("/import")
def do_import(body: ImportBody):
    from .agents.importer import import_csv
    return import_csv(body.firm_id, body.client_id, body.csv)


@app.get("/ingest/sample")
def ingest_sample():
    from .agents.ingest_agent import SAMPLE_FEED, SAMPLE_INVOICE
    return {"feed": SAMPLE_FEED, "invoice": SAMPLE_INVOICE}


@app.post("/ingest")
def do_ingest(body: IngestBody):
    from .agents.ingest_agent import ingest
    res = ingest(body.firm_id, body.client_id, body.kind, body.text, body.filename or "")
    if res.get("error"):
        raise HTTPException(400, res["error"])
    return res


@app.get("/firms/{firm_id}/recon")
def recon(firm_id: str, client_id: str, period: str | None = None):
    from .agents.recon_agent import reconcile
    return reconcile(firm_id, client_id, period)


@app.get("/firms/{firm_id}/flux")
def flux_view(firm_id: str, client_id: str, period: str | None = None):
    from .agents.flux_agent import flux
    res = flux(firm_id, client_id, period)
    if res.get("error"):
        raise HTTPException(400, res["error"])
    return res


@app.get("/firms/{firm_id}/explain/{tx_id}")
def explain(firm_id: str, tx_id: str):
    res = lineage.explain(firm_id, tx_id)
    if res.get("error"):
        raise HTTPException(404, res["error"])
    return res


@app.get("/firms/{firm_id}/scorecard")
def scorecard(firm_id: str):
    return db.get_eval_runs("code")


@app.get("/firms/{firm_id}/audit")
def audit_log(firm_id: str, limit: int = 200):
    rows = [r for r in audit.get_log() if r.get("firm_id") == firm_id][-limit:]
    return rows


@app.get("/audit/verify")
def audit_verify():
    return audit.verify_chain()


@app.get("/audit/export", response_class=PlainTextResponse)
def audit_export():
    return audit.export_csv()


@app.get("/security/check")
def security_check():
    from .evals.security_eval import run
    return run()


@app.get("/security/demo/{scenario}")
def security_demo(scenario: str):
    """Interactive threat-and-solution demos for the Trust panel."""
    firms = db.get_firms()
    f0, f1 = firms[0]["id"], firms[1]["id"]

    if scenario == "tamper":
        return audit.demo_tamper()

    if scenario == "cross_tenant":
        from .security.tenancy import TenantContext, TenantIsolationError, get_transaction_scoped
        other = db.get_transactions(f1)[0]
        ctx = TenantContext(firm_id=f0, user_role="partner")
        try:
            get_transaction_scoped(ctx, other["id"])
            outcome = {"blocked": False}
        except TenantIsolationError as e:
            outcome = {"blocked": True, "message": str(e)}
        return {"scenario": f"A user in {firms[0]['name']} tries to open a transaction belonging to {firms[1]['name']}.",
                "attempt": {"by_firm": f0, "target_firm": f1, "transaction": other["id"]},
                **outcome,
                "solution": "Every row and graph node is scoped by firm_id; access is checked against the caller's tenant."}

    if scenario == "rbac":
        checks = [(r, a, rbac.can(r, a)) for r in ["partner", "manager", "associate"]
                  for a in ["approve", "send_message", "export_audit"]]
        return {"scenario": "A junior associate tries to export the full audit trail and message clients.",
                "matrix": [{"role": r, "action": a, "allowed": ok} for r, a, ok in checks],
                "solution": "Role-based least privilege. Associates can approve and correct, but cannot export the audit log or send client messages."}

    if scenario == "encrypt":
        client = db.get_clients(f0)[0]
        token = crypto.encrypt_field(f0, client["ein"])
        try:
            crypto.decrypt_field(f1, token); cross = "decrypted (FAIL)"
        except Exception:
            cross = "could not decrypt"
        return {"scenario": "A database row leaks. Can an attacker (or another firm) read the client's EIN?",
                "plaintext": client["ein"], "ciphertext_at_rest": token[:48] + "…",
                "same_firm_decrypt": crypto.decrypt_field(f0, token),
                "other_firm_decrypt": cross,
                "solution": "PII is encrypted per tenant with a key derived from the firm. One firm's key cannot decrypt another's data."}

    if scenario == "pii":
        from .security.pii import guard
        sample = ("Hi, thanks for checking in. Your refund will be sent to account 123456789012, "
                  "and we still have your SSN 123-45-6789 on file for the filing.")
        g = guard(sample)
        return {"scenario": "A drafted client message accidentally contains an SSN and a bank account number.",
                "original": sample, **g,
                "solution": "Every client-facing message is scanned; PII is blocked and redacted before it can be sent."}

    raise HTTPException(404, "unknown scenario")


@app.get("/firms/{firm_id}/compliance")
def compliance(firm_id: str):
    from .agents.compliance_agent import scan
    return scan(firm_id)


@app.get("/firms/{firm_id}/explain/{tx_id}/narrate")
def explain_narrate(firm_id: str, tx_id: str):
    from .agents.explain_agent import narrate
    res = narrate(firm_id, tx_id)
    if res.get("error"):
        raise HTTPException(404, res["error"])
    return res


@app.get("/firms/{firm_id}/trust/health")
def trust_health(firm_id: str):
    from .agents.compliance_agent import scan as cscan
    from .evals.security_eval import run as sec
    verify = audit.verify_chain()
    comp = cscan(firm_id)
    s = sec()
    checks = [v for v in s.values() if isinstance(v, str) and (v.startswith("PASS") or v.startswith("FAIL"))]
    passed = sum(1 for v in checks if v.startswith("PASS"))
    return {"audit_chain_valid": verify.get("valid"), "audit_events": verify.get("rows"),
            "security_checks": f"{passed}/{len(checks)}",
            "compliance_findings": comp["summary"]["total"], "compliance_high": comp["summary"]["high"],
            "sod_clean": comp["summary"]["sod_clean"]}


@app.get("/firms/{firm_id}/vendor/{vendor_id}/history")
def vendor_history(firm_id: str, vendor_id: str, client_id: str):
    return get_store().coded_to_history(firm_id, vendor_id, client_id)
