"""Flag agent: real-time anomaly detection (Maxed's "watches for anomalies").

Three explainable detectors, each producing an Alert with evidence and a suggested action:
  - duplicates        same client+vendor+amount within a short window (cites the matched txn)
  - unusual_amount    far above this (client, vendor) history via robust stats (median + MAD)
  - missing_category  vendor could not be resolved / no category (needs human or client input)

Every alert carries the evidence that justifies it, so a CPA can trust (or dismiss) it in one glance.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from statistics import median
from typing import Optional

from .. import db
from ..kg.entity_resolution import normalize
from ..trust import audit

_DUP_WINDOW_DAYS = 7
_UNUSUAL_RATIO = 5.0
_MIN_HISTORY = 4


def _parse(d: str) -> date:
    y, m, dd = d.split("-")
    return date(int(y), int(m), int(dd))


def _mad(values: list[float], med: float) -> float:
    return median([abs(v - med) for v in values]) or 1.0


def detect(firm_id: str, client_id: Optional[str] = None) -> list[dict]:
    txns = db.get_transactions(firm_id, client_id=client_id)
    alerts: list[dict] = []

    # ---- duplicates: same client + normalized vendor + amount within a window
    buckets: dict[tuple, list[dict]] = defaultdict(list)
    for t in txns:
        buckets[(t["client_id"], normalize(t["vendor_raw"]), round(t["amount"], 2))].append(t)
    for key, group in buckets.items():
        if len(group) < 2:
            continue
        group = sorted(group, key=lambda t: t["date"])
        for i in range(1, len(group)):
            if abs((_parse(group[i]["date"]) - _parse(group[i - 1]["date"])).days) <= _DUP_WINDOW_DAYS:
                alerts.append({
                    "transaction_id": group[i]["id"], "type": "duplicate", "severity": "high",
                    "evidence": {"matches": group[i - 1]["id"], "vendor": group[i]["vendor_raw"],
                                 "amount": group[i]["amount"],
                                 "note": f"Same vendor and amount as {group[i-1]['id']} within {_DUP_WINDOW_DAYS} days."}})

    # ---- unusual amounts: per (client, vendor) robust outlier
    hist: dict[tuple, list[float]] = defaultdict(list)
    for t in txns:
        if t.get("vendor_id"):
            hist[(t["client_id"], t["vendor_id"])].append(t["amount"])
    for t in txns:
        if not t.get("vendor_id"):
            continue
        amts = hist[(t["client_id"], t["vendor_id"])]
        if len(amts) < _MIN_HISTORY:
            continue
        med = median(amts)
        if med > 0 and t["amount"] > _UNUSUAL_RATIO * med and t["amount"] > med + 3 * _mad(amts, med):
            alerts.append({
                "transaction_id": t["id"], "type": "unusual_amount", "severity": "medium",
                "evidence": {"amount": t["amount"], "vendor_median": round(med, 2),
                             "ratio": round(t["amount"] / med, 1),
                             "note": f"${t['amount']:.2f} is {t['amount']/med:.1f}x this vendor's median of ${med:.2f}."}})

    # ---- missing category: vendor unresolved (no canonical vendor)
    for t in txns:
        if not t.get("vendor_id"):
            alerts.append({
                "transaction_id": t["id"], "type": "missing_category", "severity": "medium",
                "evidence": {"vendor_raw": t["vendor_raw"], "amount": t["amount"],
                             "note": "Vendor could not be resolved to a known account; needs review."}})
    return alerts


def run_firm(firm_id: str, persist: bool = True) -> dict:
    alerts = detect(firm_id)
    if persist:
        for i, a in enumerate(alerts):
            db.save_alert({"id": f"{firm_id}-al{i}", "firm_id": firm_id,
                           "transaction_id": a["transaction_id"], "type": a["type"],
                           "severity": a["severity"], "evidence": a["evidence"], "status": "open"})
        audit.record("flag-agent", "anomaly_scan",
                     {"alerts": len(alerts)}, firm_id=firm_id)
    by_type: dict[str, int] = defaultdict(int)
    for a in alerts:
        by_type[a["type"]] += 1
    return {"firm_id": firm_id, "alerts": len(alerts), "by_type": dict(by_type)}
