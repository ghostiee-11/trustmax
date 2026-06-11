"""Code agent: categorize transactions to GL accounts, graph-first.

Multi-agent LangGraph pipeline per transaction:
    extractor -> graphrag_retrieve -> categorize(LLM) -> verify(critic) -> anomaly -> calibrate -> route

Graph-first: if the knowledge graph already holds a learned fact for this (vendor, client) the
categorizer follows it with high confidence; otherwise the LLM proposes a code from the chart + the
retrieved few-shot. Human approvals write `CODED_TO` facts back into the graph, which is the flywheel.
"""
from __future__ import annotations

from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph

from .. import config, db
from ..kg import retrieval
from ..ml import AnomalyDetector, heuristic_calibrate
from ..providers import get_provider
from ..trust import audit


class S(TypedDict, total=False):
    tx: dict
    accounts: list[dict]
    retrieval: dict
    guess: dict
    verifier: dict
    anomaly_score: float
    anomaly_flags: list[str]
    calibrated: float
    decision: str


def build_pipeline(firm_id: str, transactions: list[dict], accounts: list[dict]):
    provider = get_provider()
    detector = AnomalyDetector(transactions)
    codes = {a["code"] for a in accounts}
    name_by_code = {a["code"]: a["name"] for a in accounts}
    threshold = config.AUTO_APPROVE_THRESHOLD

    def n_extract(state: S) -> S:
        tx = dict(state["tx"])
        tx["vendor_raw"] = (tx.get("vendor_raw") or "").strip()
        return {"tx": tx}

    def n_retrieve(state: S) -> S:
        r = retrieval.retrieve(firm_id, state["tx"]["client_id"],
                               state["tx"]["vendor_raw"], state["tx"].get("memo", ""))
        return {"retrieval": r}

    def n_categorize(state: S) -> S:
        r = state["retrieval"]
        # convert graph candidates to the provider's example shape (similarity = candidate confidence)
        examples = [{"vendor": r.get("vendor_name") or state["tx"]["vendor_raw"], "memo": "",
                     "code": c["code"], "account_name": name_by_code.get(c["code"], ""),
                     "rationale": c["basis"], "similarity": c.get("confidence", 0.5)}
                    for c in r["candidates"]]
        g = provider.categorize(state["tx"], accounts, examples)
        if g.get("code") not in codes:
            g["code"], g["account_name"], g["confidence"] = "6900", name_by_code.get("6900", "Uncategorized"), min(g.get("confidence", 0.4), 0.4)
        else:
            g["account_name"] = name_by_code.get(g["code"], g.get("account_name", ""))
        return {"guess": g}

    def n_verify(state: S) -> S:
        examples = [{"vendor": state["retrieval"].get("vendor_name") or "", "memo": "",
                     "code": c["code"], "account_name": "", "rationale": c["basis"],
                     "similarity": c.get("confidence", 0.5)} for c in state["retrieval"]["candidates"]]
        v = provider.verify(state["tx"], state["guess"]["code"], state["guess"]["account_name"], accounts, examples)
        return {"verifier": v}

    def n_anomaly(state: S) -> S:
        risk, flags = detector.score(state["tx"])
        return {"anomaly_score": risk, "anomaly_flags": flags}

    def n_calibrate(state: S) -> S:
        cal = heuristic_calibrate(
            raw_conf=state["guess"]["confidence"],
            graph_support=state["retrieval"].get("support", 0.0),
            verifier_agreed=state["verifier"].get("agree", True),
            anomaly=state.get("anomaly_score", 0.0))
        return {"calibrated": cal}

    def n_route(state: S) -> S:
        flags = state.get("anomaly_flags", [])
        ok = state["verifier"].get("agree", True) is not False
        hard = "possible_duplicate" in flags
        grounded = state["retrieval"].get("support", 0.0) > 0
        # Ungrounded items (no learned graph fact yet) need a higher bar to auto-approve: trust is
        # earned. Once the graph has a fact, the normal threshold applies.
        bar = threshold if grounded else max(threshold, 0.95)
        auto = state["calibrated"] >= bar and ok and not hard
        return {"decision": "auto_approve" if auto else "needs_review"}

    g = StateGraph(S)
    for name, fn in [("extractor", n_extract), ("retrieve", n_retrieve), ("categorize", n_categorize),
                     ("verify", n_verify), ("anomaly", n_anomaly), ("calibrate", n_calibrate), ("route", n_route)]:
        g.add_node(name, fn)
    g.set_entry_point("extractor")
    for a, b in [("extractor", "retrieve"), ("retrieve", "categorize"), ("categorize", "verify"),
                 ("verify", "anomaly"), ("anomaly", "calibrate"), ("calibrate", "route"), ("route", END)]:
        g.add_edge(a, b)
    return g.compile(), {"provider": provider, "name_by_code": name_by_code}


def categorize_one(compiled, meta, firm_id: str, batch_id: str, tx: dict) -> dict:
    final = compiled.invoke({"tx": tx})
    guess = final["guess"]
    r = final["retrieval"]
    cat = {
        "transaction_id": tx["id"], "firm_id": firm_id, "batch_id": batch_id,
        "client_id": tx["client_id"], "vendor_id": r.get("vendor_id"),
        "predicted_code": guess["code"], "predicted_account_name": guess["account_name"],
        "raw_confidence": round(float(guess["confidence"]), 3),
        "calibrated_confidence": round(float(final["calibrated"]), 3),
        "graph_support": r.get("support", 0.0), "er_method": r.get("er_method"),
        "anomaly_score": round(float(final.get("anomaly_score", 0.0)), 3),
        "anomaly_flags": final.get("anomaly_flags", []),
        "verifier_agreed": final["verifier"].get("agree", True),
        "rationale": guess.get("rationale", ""),
        "reasoning_path": r.get("reasoning_path", []),
        "provider": meta["provider"].name, "model": meta["provider"].model,
        "decision": final["decision"],
        "status": "auto_approved" if final["decision"] == "auto_approve" else "pending",
        "final_code": guess["code"] if final["decision"] == "auto_approve" else None,
    }
    db.save_categorization(cat)
    return cat


def run_batch(firm_id: str, batch_id: str, limit: Optional[int] = None) -> list[dict]:
    accounts = db.get_gl_accounts(firm_id)
    txns = db.get_transactions(firm_id, batch_id=batch_id)
    if limit:
        txns = txns[:limit]
    compiled, meta = build_pipeline(firm_id, txns, accounts)
    out = []
    for tx in txns:
        cat = categorize_one(compiled, meta, firm_id, batch_id, tx)
        action = "auto_approve" if cat["status"] == "auto_approved" else "route_to_human"
        audit.record("code-agent", action, {
            "transaction_id": cat["transaction_id"], "code": cat["predicted_code"],
            "calibrated_confidence": cat["calibrated_confidence"], "graph_support": cat["graph_support"]},
            firm_id=firm_id)
        out.append(cat)
    return out
