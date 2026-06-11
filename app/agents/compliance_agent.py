"""Compliance agent: a background reviewer that watches the firm for governance risk.

It reads the tamper-evident audit log plus the categorizations and alerts, and surfaces typed findings
the way a SOC / audit analyst would: high-value decisions that slipped through automatically,
segregation-of-duties (self-approval), approval concentration, unresolved high-severity anomalies, and
vendors with an unusually high correction rate. Each finding carries evidence and a recommendation.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict

from .. import db
from ..trust import audit

HIGH_VALUE = 2500.0           # auto-approvals above this should have human sign-off
CONCENTRATION = 100           # one approver doing this many reviews is a SoD risk
CORRECTION_RATE = 0.40        # a vendor corrected this often signals a coding-policy gap


def _firm_log(firm_id: str) -> list[dict]:
    rows = []
    for r in audit.get_log():
        if r.get("firm_id") != firm_id:
            continue
        try:
            payload = json.loads(r["payload"])
        except Exception:
            payload = {}
        rows.append({**r, "payload": payload})
    return rows


def scan(firm_id: str) -> dict:
    findings: list[dict] = []
    txns = {t["id"]: t for t in db.get_transactions(firm_id)}
    cats = db.get_categorizations(firm_id)
    log = _firm_log(firm_id)

    # 1) high-value auto-approvals
    hv = []
    for c in cats:
        if c.get("status") == "auto_approved":
            amt = (txns.get(c["transaction_id"]) or {}).get("amount", 0) or 0
            if amt >= HIGH_VALUE:
                hv.append((c["transaction_id"], amt, c.get("predicted_code")))
    if hv:
        hv.sort(key=lambda x: -x[1])
        findings.append({
            "type": "high_value_auto_approve", "severity": "medium", "count": len(hv),
            "detail": f"{len(hv)} transactions over ${HIGH_VALUE:,.0f} were auto-approved without human sign-off.",
            "evidence": [{"transaction_id": t, "amount": round(a, 2), "code": c} for t, a, c in hv[:5]],
            "recommendation": f"Require partner sign-off for any decision above ${HIGH_VALUE:,.0f}."})

    # 2) segregation of duties: same actor created AND approved a transaction
    creators, approvers = {}, {}
    for r in log:
        tid = r["payload"].get("transaction_id")
        if not tid:
            continue
        if r["action"] in ("auto_approve", "route_to_human"):
            creators[tid] = r["actor"]
        if r["action"] in ("approve", "correct"):
            approvers[tid] = r["actor"]
    sod = [tid for tid in approvers if creators.get(tid) and creators[tid] == approvers[tid]]
    if sod:
        findings.append({
            "type": "self_approval_sod", "severity": "high", "count": len(sod),
            "detail": f"{len(sod)} transactions were created and approved by the same actor (segregation of duties).",
            "evidence": [{"transaction_id": t} for t in sod[:5]],
            "recommendation": "Enforce that the creator and approver of a decision must differ."})

    # 3) approval concentration
    counts = Counter(r["actor"] for r in log if r["action"] in ("approve", "correct"))
    for actor, n in counts.items():
        if n >= CONCENTRATION:
            findings.append({
                "type": "approval_concentration", "severity": "medium", "count": n,
                "detail": f"'{actor}' performed {n} approvals; concentration / segregation-of-duties risk.",
                "evidence": [{"actor": actor, "approvals": n}],
                "recommendation": "Distribute review across staff and cap per-reviewer volume."})

    # 4) unresolved high-severity anomalies
    from .anomaly_agent import detect
    alerts = db.get_alerts(firm_id) or detect(firm_id)
    open_high = [a for a in alerts if a.get("severity") == "high" and a.get("status", "open") == "open"]
    if open_high:
        findings.append({
            "type": "unresolved_high_alerts", "severity": "high", "count": len(open_high),
            "detail": f"{len(open_high)} high-severity anomalies (likely duplicate payments) are still open.",
            "evidence": [{"transaction_id": a["transaction_id"], "note": a["evidence"].get("note", "")} for a in open_high[:5]],
            "recommendation": "Clear duplicate-payment alerts before the books are closed."})

    # 5) vendors with a high correction rate
    seen, corrected = defaultdict(int), defaultdict(int)
    for c in cats:
        vid = c.get("vendor_id")
        if not vid:
            continue
        seen[vid] += 1
        if c.get("status") == "corrected":
            corrected[vid] += 1
    vname = {v["id"]: v["canonical_name"] for v in db.get_vendors(firm_id)}
    for vid, n in seen.items():
        if n >= 5 and corrected[vid] / n >= CORRECTION_RATE:
            findings.append({
                "type": "vendor_correction_rate", "severity": "low", "count": corrected[vid],
                "detail": f"{vname.get(vid, vid)} was corrected {corrected[vid]}/{n} times; coding-policy gap.",
                "evidence": [{"vendor": vname.get(vid, vid), "corrected": corrected[vid], "of": n}],
                "recommendation": "Add an explicit coding rule for this vendor."})

    sev_rank = {"high": 3, "medium": 2, "low": 1}
    findings.sort(key=lambda f: -sev_rank.get(f["severity"], 0))
    return {
        "firm_id": firm_id,
        "findings": findings,
        "summary": {
            "total": len(findings),
            "high": sum(1 for f in findings if f["severity"] == "high"),
            "sod_clean": not sod,
            "scanned_events": len(log),
        },
    }
