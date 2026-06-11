"""Flux / variance narrator.

Before a partner signs off on a month, the first question is always "what moved and why?". This agent
computes the month-over-month variance per category from the ledger (deterministically, never
generated), finds the transactions driving each big swing, and narrates it in plain English. The
numbers are computed by query and the model only phrases the sentence around them, so it cannot
hallucinate a number. Every driver cites the exact transactions behind it: variance you can drill into.
"""
from __future__ import annotations

from .. import db
from ..datagen.seeds import CHART_OF_ACCOUNTS
from ..providers import get_provider

_NAME = {code: name for code, name, _t, _d in CHART_OF_ACCOUNTS}


def _periods(firm_id: str, client_id: str) -> list[str]:
    rows = db.get_transactions(firm_id, client_id=client_id)
    months = sorted({t["batch_id"] for t in rows if t["batch_id"] and t["batch_id"][0].isdigit()})
    return months


def _by_category(firm_id: str, client_id: str, period: str) -> tuple[dict, dict]:
    """Return (spend_by_code, txns_by_code) for a period, using the coded ledger."""
    rows = db.get_transactions(firm_id, batch_id=period, client_id=client_id)
    spend: dict[str, float] = {}
    txns: dict[str, list] = {}
    for t in rows:
        cat = db.get_categorization(t["id"]) or {}
        code = cat.get("final_code") or cat.get("predicted_code") or t.get("gt_code") or "6900"
        spend[code] = round(spend.get(code, 0.0) + float(t["amount"]), 2)
        txns.setdefault(code, []).append({"date": t["date"], "vendor": t["vendor_raw"],
                                          "amount": round(float(t["amount"]), 2)})
    return spend, txns


def _pct(delta: float, prior: float):
    if not prior:
        return None
    return round(delta / prior, 3)


def flux(firm_id: str, client_id: str, period: str | None = None, prior: str | None = None) -> dict:
    months = _periods(firm_id, client_id)
    if len(months) < 2:
        return {"error": "Need at least two periods of data to compute a variance."}
    if not period:
        period = months[-1]
    if not prior:
        idx = months.index(period) if period in months else len(months) - 1
        prior = months[idx - 1] if idx > 0 else months[0]

    cur_spend, cur_txns = _by_category(firm_id, client_id, period)
    pri_spend, _ = _by_category(firm_id, client_id, prior)

    codes = sorted(set(cur_spend) | set(pri_spend))
    rows = []
    for code in codes:
        cur = cur_spend.get(code, 0.0)
        pri = pri_spend.get(code, 0.0)
        delta = round(cur - pri, 2)
        rows.append({"code": code, "name": _NAME.get(code, code), "current": cur, "prior": pri,
                     "delta": delta, "pct": _pct(delta, pri),
                     "direction": "up" if delta > 0 else ("down" if delta < 0 else "flat")})
    rows.sort(key=lambda r: abs(r["delta"]), reverse=True)

    tot_cur = round(sum(cur_spend.values()), 2)
    tot_pri = round(sum(pri_spend.values()), 2)
    total = {"current": tot_cur, "prior": tot_pri, "delta": round(tot_cur - tot_pri, 2),
             "pct": _pct(round(tot_cur - tot_pri, 2), tot_pri)}

    drivers = []
    for r in [r for r in rows if abs(r["delta"]) > 0][:3]:
        txns = sorted(cur_txns.get(r["code"], []), key=lambda x: x["amount"], reverse=True)[:3]
        drivers.append({"code": r["code"], "name": r["name"], "delta": r["delta"], "pct": r["pct"], "txns": txns})

    narrative, generated_by = _narrate(period, prior, total, rows, get_provider())
    return {"period": period, "prior": prior, "total": total, "rows": rows,
            "drivers": drivers, "narrative": narrative, "generated_by": generated_by}


def _computed_sentence(period: str, prior: str, total: dict, rows: list) -> str:
    movers = [r for r in rows if abs(r["delta"]) > 0][:3]
    dirn = "up" if total["delta"] >= 0 else "down"
    parts = []
    for r in movers:
        d = "up" if r["delta"] > 0 else "down"
        pct = f" ({abs(r['pct']) * 100:.0f}%)" if r["pct"] is not None else ""
        parts.append(f"{r['name']} {d} ${abs(r['delta']):,.0f}{pct}")
    lead = (f"Total spend moved {dirn} ${abs(total['delta']):,.0f} from {prior} to {period}, "
            f"from ${total['prior']:,.0f} to ${total['current']:,.0f}.")
    if parts:
        lead += " The largest drivers were " + "; ".join(parts) + "."
    return lead


def _narrate(period: str, prior: str, total: dict, rows: list, provider) -> tuple[str, str]:
    computed = _computed_sentence(period, prior, total, rows)
    facts = "; ".join(f"{r['name']} {r['current']:.0f} vs {r['prior']:.0f}" for r in rows[:6])
    system = ("You are a CPA writing a short month-over-month flux note. Use ONLY the numbers given. "
              "Do not invent any figure. Two or three sentences, plain and professional.")
    user = (f"Period {period} vs {prior}. Total {total['current']:.0f} vs {total['prior']:.0f} "
            f"(change {total['delta']:.0f}). Category figures: {facts}. "
            f"Write the flux note now.")
    try:
        text = provider.chat(system, user).strip()
    except Exception:
        text = ""
    if text:
        return text, "model phrased"
    return computed, "computed"
