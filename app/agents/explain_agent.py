"""Explainability agent: narrate WHY a transaction was coded the way it was, in plain English.

Strictly grounded: it is given the lineage (the graph reasoning path, the learned fact, the decision)
and may only restate those facts. The amount and account code in the narrative must match the lineage,
or we fall back to the literal reasoning path. Same no-hallucination posture as Ed.
"""
from __future__ import annotations

import re

from ..kg import lineage
from ..providers import get_provider


def _strip_dashes(s: str) -> str:
    return s.replace("—", ", ").replace("–", ", ")


def narrate(firm_id: str, transaction_id: str) -> dict:
    lin = lineage.explain(firm_id, transaction_id)
    if lin.get("error"):
        return lin
    tx = lin.get("transaction", {})
    dec = lin.get("decision", {})
    path = lin.get("reasoning_path", []) or []
    code = dec.get("code")
    amount = tx.get("amount")
    literal = (f"{tx.get('vendor_raw')} for ${amount:,.2f} was coded to {code}"
               + (f" because {path[0][0].lower()}{path[0][1:]}" if path else ".")) if amount is not None else "; ".join(path)

    provider = get_provider()
    if provider.name != "groq" or code is None:
        return {"narrative": literal, "grounded": True, "generated_by": "verified template", "lineage": lin}

    system = ("You are an audit explainer for a CPA firm. In 1 to 2 plain sentences, explain WHY this "
              "transaction was coded this way, using ONLY the facts provided. You MUST include the exact "
              "amount and the account code given, and MUST NOT invent any other numbers, dates, vendors, "
              "or accounts. Do not use em dashes.")
    user = (f"Vendor: {tx.get('vendor_raw')}\nAmount: ${amount:,.2f}\nCoded to account: {code} "
            f"({dec.get('account')})\nReasoning path: {' | '.join(path) or 'cold start'}\n"
            f"Learned graph fact: {lin.get('graph_fact')}")
    try:
        out = _strip_dashes(provider.chat(system, user).strip())
    except Exception:
        out = literal
    nums = {float(n.replace(",", "")) for n in re.findall(r"[\d,]+\.?\d*", out.replace("$", ""))
            if n.replace(",", "").replace(".", "").isdigit()}
    grounded = (str(code) in out) and (round(float(amount), 2) in nums or float(amount) in nums)
    if not grounded:
        out = literal
    return {"narrative": out, "grounded": grounded, "generated_by": provider.model if grounded else "verified template",
            "lineage": lin}
