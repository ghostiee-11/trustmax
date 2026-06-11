"""Model-agnostic LLM provider adapter.

The pipeline talks to a small task interface (categorize / verify / draft_message). Swapping the
backing model is a one-line env change, which mirrors Maxed's "build on the open-source AI ecosystem,
pick the models, string them into a coherent stack" mandate.

Providers:
  - groq   : open-weight Llama models via Groq (default; needs GROQ_API_KEY)
  - mock   : a fully offline, deterministic stand-in so the flywheel runs with zero network/keys.
             Its base priors deliberately DISAGREE with the firm's idiosyncratic conventions, so the
             learning loop has something real to correct. When firm memory is supplied it follows it,
             which is exactly how the real model behaves once given few-shot examples.

openai/anthropic are intentionally left as obvious extension points (same interface).
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any, Optional

from .. import config


# ---------------------------------------------------------------------------- base
class LLMProvider(ABC):
    name: str = "base"
    model: str = ""

    @abstractmethod
    def categorize(self, tx: dict, accounts: list[dict], examples: list[dict]) -> dict:
        """Return {code, account_name, confidence, rationale}."""

    @abstractmethod
    def verify(self, tx: dict, proposed_code: str, proposed_name: str,
               accounts: list[dict], examples: list[dict]) -> dict:
        """Critic/judge agent. Return {agree: bool, note: str, suggested_code: str|None}."""

    @abstractmethod
    def draft_message(self, tx: dict, reason: str) -> dict:
        """Ed agent. Return {subject, body} for an approval-gated client message."""

    def chat(self, system: str, user: str) -> str:
        """Free-form phrasing. Returns "" when the backend has no live model."""
        return ""


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of an LLM response, tolerating prose/code fences."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return {}


# ---------------------------------------------------------------------------- groq
class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(self) -> None:
        from langchain_groq import ChatGroq
        self.model = config.GROQ_MODEL
        self._llm = ChatGroq(model=config.GROQ_MODEL, api_key=config.GROQ_API_KEY, temperature=0)

    def _chat(self, system: str, user: str) -> str:
        resp = self._llm.invoke([("system", system), ("human", user)])
        return resp.content if isinstance(resp.content, str) else str(resp.content)

    def chat(self, system: str, user: str) -> str:
        return self._chat(system, user)

    @staticmethod
    def _accounts_block(accounts: list[dict]) -> str:
        return "\n".join(f"  {a['code']}  {a['name']} - {a.get('description','')}" for a in accounts)

    @staticmethod
    def _examples_block(examples: list[dict]) -> str:
        if not examples:
            return "  (no prior firm-approved examples for similar transactions yet)"
        return "\n".join(
            f"  vendor='{e['vendor']}' memo='{e['memo']}' -> {e['code']} {e['account_name']} "
            f"(approved by a human; {e['rationale']})"
            for e in examples
        )

    def categorize(self, tx: dict, accounts: list[dict], examples: list[dict]) -> dict:
        system = (
            "You are Max, an expert bookkeeping agent for a CPA firm. Assign the single best GL code "
            "to a transaction using ONLY the firm's chart of accounts. Firms have idiosyncratic coding "
            "conventions; the human-approved examples reflect THIS firm's conventions and OUTRANK your "
            "generic intuition. Return STRICT JSON: "
            '{"code": "...", "account_name": "...", "confidence": 0.0-1.0, "rationale": "..."}. '
            "confidence reflects your genuine certainty given the chart and the examples."
        )
        user = (
            f"CHART OF ACCOUNTS:\n{self._accounts_block(accounts)}\n\n"
            f"FIRM-APPROVED SIMILAR EXAMPLES (authoritative):\n{self._examples_block(examples)}\n\n"
            f"TRANSACTION:\n  vendor='{tx['vendor']}' memo='{tx.get('memo','')}' amount={tx['amount']} date={tx['date']}\n\n"
            "Return the JSON now."
        )
        out = _extract_json(self._chat(system, user))
        return {
            "code": str(out.get("code", "")).strip(),
            "account_name": str(out.get("account_name", "")).strip(),
            "confidence": float(out.get("confidence", 0.5) or 0.5),
            "rationale": str(out.get("rationale", "")).strip(),
        }

    def verify(self, tx: dict, proposed_code: str, proposed_name: str,
               accounts: list[dict], examples: list[dict]) -> dict:
        system = (
            "You are a meticulous review agent auditing another agent's GL coding. Be skeptical. "
            "If the firm-approved examples imply a different code, disagree. Return STRICT JSON: "
            '{"agree": true/false, "note": "...", "suggested_code": "..." or null}.'
        )
        user = (
            f"CHART:\n{self._accounts_block(accounts)}\n\n"
            f"FIRM-APPROVED EXAMPLES:\n{self._examples_block(examples)}\n\n"
            f"TRANSACTION: vendor='{tx['vendor']}' memo='{tx.get('memo','')}' amount={tx['amount']}\n"
            f"PROPOSED: {proposed_code} {proposed_name}\n\nReturn the JSON now."
        )
        out = _extract_json(self._chat(system, user))
        return {
            "agree": bool(out.get("agree", True)),
            "note": str(out.get("note", "")).strip(),
            "suggested_code": (str(out["suggested_code"]).strip() if out.get("suggested_code") else None),
        }

    def draft_message(self, tx: dict, reason: str) -> dict:
        system = (
            "You are Ed, a CPA firm's client-facing assistant. Draft a short, warm, professional "
            "message to a client. NEVER send without human approval. Return STRICT JSON: "
            '{"subject": "...", "body": "..."}.'
        )
        user = (
            f"Transaction needing clarification: vendor='{tx['vendor']}' memo='{tx.get('memo','')}' "
            f"amount={tx['amount']} date={tx['date']}.\nReason we need the client: {reason}\n"
            "Ask the client politely for what is needed. Keep it under 90 words. Return the JSON now."
        )
        out = _extract_json(self._chat(system, user))
        return {
            "subject": str(out.get("subject", "Quick question about a transaction")).strip(),
            "body": str(out.get("body", "")).strip(),
        }


# ---------------------------------------------------------------------------- mock
# Generic priors of a "base" model that has NOT learned this firm's conventions.
# Format: keyword -> (code, account_name, confidence). These intentionally differ from the firm's
# ground-truth rules on the idiosyncratic vendors, so the flywheel has real errors to correct.
_GENERIC_PRIORS: list[tuple[str, tuple[str, str, float]]] = [
    # vendors a generic model codes "intuitively" but WRONG for this firm:
    ("apex", ("6400", "Office Supplies", 0.55)),        # firm: 5000 COGS (client-reimbursable)
    ("costco", ("6020", "Meals & Entertainment", 0.58)),# firm: 6400 Office Supplies
    ("amazon web", ("6300", "Software Subscriptions", 0.8)),  # correct-ish
    ("amazon", ("6400", "Office Supplies", 0.5)),       # firm: 6400 too, but low confidence (ambiguous)
    ("chevron", ("6010", "Travel", 0.45)),              # firm: 6010 Travel; low conf
    ("shell", ("6010", "Travel", 0.45)),
    ("upwork", ("6500", "Professional Fees", 0.55)),    # firm: 6550 Contract Labor
    ("fiverr", ("6500", "Professional Fees", 0.55)),
    ("meta", ("6300", "Software Subscriptions", 0.5)),  # firm: 6100 Advertising
    ("facebook", ("6100", "Advertising & Marketing", 0.7)),
    ("fedex", ("6400", "Office Supplies", 0.5)),        # firm: 6420 Postage & Shipping
    ("ups store", ("6400", "Office Supplies", 0.5)),
    # vendors a generic model gets right with decent confidence:
    ("uber eats", ("6020", "Meals & Entertainment", 0.85)),
    ("doordash", ("6020", "Meals & Entertainment", 0.85)),
    ("uber", ("6010", "Travel", 0.82)),
    ("lyft", ("6010", "Travel", 0.82)),
    ("delta", ("6010", "Travel", 0.88)),
    ("united air", ("6010", "Travel", 0.88)),
    ("marriott", ("6010", "Travel", 0.84)),
    ("notion", ("6300", "Software Subscriptions", 0.9)),
    ("figma", ("6300", "Software Subscriptions", 0.9)),
    ("slack", ("6300", "Software Subscriptions", 0.9)),
    ("github", ("6300", "Software Subscriptions", 0.9)),
    ("google ads", ("6100", "Advertising & Marketing", 0.86)),
    ("staples", ("6400", "Office Supplies", 0.88)),
    ("wework", ("6700", "Rent & Occupancy", 0.8)),
    ("verizon", ("6600", "Utilities & Telecom", 0.85)),
    ("comcast", ("6600", "Utilities & Telecom", 0.85)),
    ("starbucks", ("6020", "Meals & Entertainment", 0.8)),
    ("blue bottle", ("6020", "Meals & Entertainment", 0.78)),
]


class MockProvider(LLMProvider):
    """Deterministic offline model. Follows firm memory when available, else uses generic priors."""
    name = "mock"
    model = "mock-rules-v1"

    def categorize(self, tx: dict, accounts: list[dict], examples: list[dict]) -> dict:
        vendor = (tx.get("vendor", "") + " " + tx.get("memo", "")).lower()

        # 1) If firm memory has a confident match, follow it (this is the "learned" behavior).
        if examples:
            best = examples[0]
            if best.get("similarity", 0) >= 0.55:
                conf = 0.90 + min(0.07, (best["similarity"] - 0.55) * 0.2)
                return {
                    "code": best["code"],
                    "account_name": best["account_name"],
                    "confidence": round(conf, 3),
                    "rationale": f"Matches firm-approved convention for similar '{best['vendor']}'.",
                }

        # 2) Otherwise fall back to generic priors (firm-naive).
        for key, (code, name, conf) in _GENERIC_PRIORS:
            if key in vendor:
                return {"code": code, "account_name": name, "confidence": conf,
                        "rationale": "Generic prior (no firm-specific example seen yet)."}

        # 3) Unknown vendor: low-confidence guess.
        return {"code": "6900", "account_name": "Uncategorized / Ask Client", "confidence": 0.35,
                "rationale": "Unfamiliar vendor; no prior and no clear generic category."}

    def verify(self, tx: dict, proposed_code: str, proposed_name: str,
               accounts: list[dict], examples: list[dict]) -> dict:
        # Critic sides with firm memory when it disagrees with the proposal.
        if examples and examples[0].get("similarity", 0) >= 0.6 and examples[0]["code"] != proposed_code:
            return {"agree": False,
                    "note": f"Firm-approved convention suggests {examples[0]['code']}.",
                    "suggested_code": examples[0]["code"]}
        if proposed_code == "6900":
            return {"agree": False, "note": "Uncategorized; needs human or client input.", "suggested_code": None}
        return {"agree": True, "note": "Consistent with available evidence.", "suggested_code": None}

    def draft_message(self, tx: dict, reason: str) -> dict:
        return {
            "subject": f"Quick question about your {tx['vendor']} charge",
            "body": (
                f"Hi,\n\nWe're finalizing your books and want to code one item correctly. "
                f"Could you confirm what the {tx['vendor']} charge of ${tx['amount']:.2f} on "
                f"{tx['date']} was for? {reason}\n\nThanks so much,\nYour accounting team"
            ),
        }


# ---------------------------------------------------------------------------- factory
_CACHE: dict[str, LLMProvider] = {}


def get_provider() -> LLMProvider:
    prov = config.effective_provider()
    if prov in _CACHE:
        return _CACHE[prov]
    if prov == "groq":
        inst: LLMProvider = GroqProvider()
    else:
        inst = MockProvider()
    _CACHE[prov] = inst
    return inst
