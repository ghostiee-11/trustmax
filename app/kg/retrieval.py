"""GraphRAG retrieval for transaction coding.

For a transaction we resolve the vendor (entity resolution), then pull the firm's *learned* coding
facts from the knowledge graph and turn them into prioritized, explainable candidates:

  client_history   this client has coded this vendor before (strongest)
  firm_convention  other clients of this firm code this vendor consistently
  generic_prior    the vendor's default category (weak, used before anything is learned)

The result feeds the categorizer as authoritative few-shot context and carries a reasoning path for
audit. As approvals accumulate, the graph fills in and `support` rises, which is the flywheel.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

from .entity_resolution import Resolver
from .store import get_store

_RESOLVERS: dict[str, Resolver] = {}


def _resolver(firm_id: str) -> Resolver:
    if firm_id not in _RESOLVERS:
        _RESOLVERS[firm_id] = Resolver(firm_id)
    return _RESOLVERS[firm_id]


def reset_cache() -> None:
    _RESOLVERS.clear()


def retrieve(firm_id: str, client_id: str, vendor_raw: str, memo: str = "") -> dict:
    er = _resolver(firm_id).resolve(vendor_raw)
    vendor_id = er.get("vendor_id")
    vendor_name = er.get("canonical_name")
    candidates: list[dict] = []
    reasoning: list[str] = []

    if vendor_id:
        store = get_store()
        # 1) client-specific learned fact
        cf = store.get_current_code(firm_id, vendor_id, client_id)
        if cf:
            candidates.append({"code": cf["code"], "basis": "client_history",
                               "confidence": cf.get("confidence", 0.9), "source": cf.get("source")})
            reasoning.append(f"This client has previously coded {vendor_name} to {cf['code']} "
                             f"(approved: {cf.get('source')}).")
        # 2) firm-wide convention across clients
        facts = [f for f in store.vendor_open_facts(firm_id, vendor_id) if f["client_id"] != client_id]
        if facts:
            counts = Counter(f["code"] for f in facts)
            code, n = counts.most_common(1)[0]
            support = n / len(facts)
            candidates.append({"code": code, "basis": "firm_convention",
                               "confidence": round(0.6 + 0.35 * support, 3),
                               "support": f"{n}/{len(facts)} clients"})
            reasoning.append(f"{n} of {len(facts)} other clients code {vendor_name} to {code}.")
        # 3) generic prior
        if er.get("default_code"):
            candidates.append({"code": er["default_code"], "basis": "generic_prior", "confidence": 0.5})
            reasoning.append(f"Default category for {vendor_name} is {er['default_code']}.")
    else:
        reasoning.append(f"Vendor '{vendor_raw}' could not be resolved; needs review.")

    # graph support = strongest learned (non-generic) signal
    learned = [c["confidence"] for c in candidates if c["basis"] in ("client_history", "firm_convention")]
    support = max(learned) if learned else 0.0

    return {
        "vendor_id": vendor_id, "vendor_name": vendor_name, "er_method": er.get("method"),
        "er_confidence": er.get("confidence", 0.0),
        "candidates": candidates, "support": round(support, 3),
        "reasoning_path": reasoning,
    }


def few_shot_block(retrieval: dict) -> str:
    """Render retrieval candidates as authoritative few-shot text for the categorizer LLM."""
    if not retrieval["candidates"]:
        return "  (no learned facts for this vendor yet)"
    lines = []
    for c in retrieval["candidates"]:
        extra = c.get("support", c.get("source", ""))
        lines.append(f"  {retrieval['vendor_name']} -> {c['code']} [{c['basis']}{(' ' + str(extra)) if extra else ''}]")
    return "\n".join(lines)
