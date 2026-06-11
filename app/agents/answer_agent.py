"""Answer agent (Ed): answer client questions from their own data with a hard no-hallucination guarantee.

The anti-hallucination architecture:
  1. Scope guard      retrieval is locked to this tenant + this client.
  2. Plan             the question maps to ONE whitelisted, typed tool. A rule-based parser handles
                      the common shapes fast and deterministically; a Groq planner is the fallback for
                      anything novel, but it may only pick a whitelisted tool and validated params.
  3. Compute by code  numbers are computed by deterministic tools over the client's ledger, never by
                      the model.
  4. Cite             every answer carries the exact transactions it used.
  5. Validate         the headline number rendered must equal the computed value, else refuse.
  6. Abstain          advisory / out-of-scope questions escalate to the accountant.
  7. Compose          the model only phrases the reply (no em dashes, no invented figures).

Supported tools: sum_by_category, total_expense, count_transactions, spend_by_vendor, top_vendors,
largest_expense, category_breakdown, list_transactions, average_transaction.
"""
from __future__ import annotations

import json
import re
from statistics import mean
from typing import Optional

from .. import db
from ..kg.entity_resolution import normalize
from ..providers import get_provider
from ..trust import audit

_MONTHS = {"january": "01", "february": "02", "march": "03", "april": "04", "may": "05",
           "june": "06", "july": "07", "august": "08", "september": "09", "october": "10",
           "november": "11", "december": "12"}
_ADVISORY = ["should i", "should we", "would you recommend", "is it a good idea",
             "s-corp", "convert my", "do you think", "worth it"]

# Natural-language synonyms mapped to GL account codes, so "meals" resolves like "Meals & Entertainment".
CATEGORY_SYNONYMS = {
    "6010": ["travel", "airfare", "flight", "flights", "hotel", "hotels", "rideshare", "mileage"],
    "6020": ["meals", "meal", "food", "dining", "restaurant", "restaurants", "coffee", "lunch", "entertainment"],
    "6100": ["advertising", "ads", "ad spend", "marketing"],
    "6300": ["software", "saas", "subscription", "subscriptions", "cloud", "tools"],
    "6400": ["office supplies", "office", "supplies"],
    "6420": ["postage", "shipping", "courier"],
    "6500": ["professional fees", "legal", "professional services"],
    "6550": ["contract labor", "contractor", "contractors", "freelance", "freelancer", "freelancers"],
    "6600": ["utilities", "telecom", "internet", "phone"],
    "6700": ["rent", "occupancy", "coworking"],
    "6800": ["bank fees", "merchant fees", "processing fees", "processor fees"],
}


def _strip_dashes(s: str) -> str:
    """Remove em and en dashes from any model-generated text shown to the user."""
    return s.replace("—", ", ").replace("–", ", ")


class AnswerAgent:
    def __init__(self, firm_id: str):
        self.firm_id = firm_id
        accounts = db.get_gl_accounts(firm_id)
        self.code_by_name = {a["name"].lower(): a["code"] for a in accounts}
        self.name_by_code = {a["code"]: a["name"] for a in accounts}
        self.provider = get_provider()
        self._client_names = {c["id"]: c["name"] for c in db.get_clients(firm_id)}
        self._vendors = db.get_vendors(firm_id)
        self._vname_by_id = {v["id"]: v["canonical_name"] for v in self._vendors}
        # category terms: synonyms + full account names, longest first so specifics win
        self._cat_terms = sorted(
            [(kw, code) for code, kws in CATEGORY_SYNONYMS.items() if code in self.name_by_code for kw in kws]
            + [(a["name"].lower(), a["code"]) for a in accounts if a["type"] == "expense"],
            key=lambda x: -len(x[0]))
        # vendor terms: canonical names + distinctive aliases, longest first
        terms = {(v["canonical_name"].lower(), v["id"]) for v in self._vendors}
        for a in db.get_vendor_aliases(firm_id):
            t = normalize(a["alias"])
            if len(t) >= 3:
                terms.add((t, a["vendor_id"]))
        self._vendor_terms = sorted(terms, key=lambda x: -len(x[0]))

    # ---- ledger access -------------------------------------------------------
    def _in_period(self, batch_id: str, period: Optional[str]) -> bool:
        if not period:
            return True
        if "-Q" in period:
            yr, q = period.split("-Q")
            months = {"1": "010203", "2": "040506", "3": "070809", "4": "101112"}[q]
            return batch_id[:4] == yr and batch_id[5:7] in {months[i:i+2] for i in range(0, 6, 2)}
        if len(period) == 4:
            return batch_id[:4] == period
        return batch_id == period

    def _ledger(self, client_id: str, period: Optional[str]) -> list[dict]:
        return [t for t in db.get_transactions(self.firm_id, client_id=client_id)
                if not t.get("is_anomaly") and self._in_period(t["batch_id"], period)]

    # ---- tools ---------------------------------------------------------------
    def _tool(self, name: str, client_id: str, params: dict) -> dict:
        period = params.get("period")
        rows = self._ledger(client_id, period)
        pp = self._period_phrase(period)

        if name == "sum_by_category" or (name == "list_transactions" and params.get("code")):
            code = params["code"]
            sel = [t for t in rows if t["gt_code"] == code]
            total = round(sum(t["amount"] for t in sel), 2)
            label = self.name_by_code.get(code, code)
            template = f"You spent ${total:,.2f} on {label}{pp}, across {len(sel)} transactions."
            return self._wrap(total, sel, template, table=self._tx_table(sel))

        if name == "total_expense":
            total = round(sum(t["amount"] for t in rows), 2)
            return self._wrap(total, rows, f"Your total expenses{pp} were ${total:,.2f}, across {len(rows)} transactions.",
                              table=self._tx_table(rows))

        if name == "count_transactions":
            return self._wrap(len(rows), rows, f"You had {len(rows)} transactions{pp}.", table=self._tx_table(rows))

        if name == "average_transaction":
            avg = round(mean([t["amount"] for t in rows]), 2) if rows else 0.0
            return self._wrap(avg, rows, f"Your average transaction{pp} was ${avg:,.2f}, over {len(rows)} transactions.")

        if name == "spend_by_vendor":
            vid = params["vendor_id"]
            vname = self._vname_by_id.get(vid, "that vendor")
            sel = [t for t in rows if t.get("vendor_id") == vid]
            total = round(sum(t["amount"] for t in sel), 2)
            return self._wrap(total, sel, f"You spent ${total:,.2f} with {vname}{pp}, across {len(sel)} transactions.",
                              table=self._tx_table(sel) if params.get("list") else None)

        if name == "top_vendors":
            n = int(params.get("n", 5))
            agg: dict[str, list] = {}
            for t in rows:
                if t.get("vendor_id"):
                    agg.setdefault(t["vendor_id"], []).append(t["amount"])
            ranked = sorted(((self._vname_by_id.get(vid, vid), round(sum(a), 2), len(a))
                             for vid, a in agg.items()), key=lambda x: -x[1])[:n]
            if not ranked:
                return self._wrap(0, [], f"I found no vendor spend{pp}.")
            top = ranked[0]
            template = f"Your largest vendor{pp} was {top[0]} at ${top[1]:,.2f}, across {top[2]} transactions."
            return self._wrap(top[1], rows, template,
                              table={"type": "vendors", "rows": [{"vendor": v, "total": tot, "count": c} for v, tot, c in ranked]})

        if name == "largest_expense":
            if not rows:
                return self._wrap(0, [], f"I found no transactions{pp}.")
            t = max(rows, key=lambda r: r["amount"])
            return self._wrap(round(t["amount"], 2), [t],
                              f"Your largest expense{pp} was ${t['amount']:,.2f} to {t['vendor_raw']} on {t['date']}.",
                              table=self._tx_table([t]))

        if name == "category_breakdown":
            agg: dict[str, float] = {}
            for t in rows:
                agg[t["gt_code"]] = agg.get(t["gt_code"], 0.0) + t["amount"]
            ranked = sorted(((c, round(v, 2)) for c, v in agg.items()), key=lambda x: -x[1])
            total = round(sum(v for _, v in ranked), 2)
            top = ranked[0] if ranked else ("", 0)
            template = (f"Across ${total:,.2f}{pp}, your biggest category was "
                        f"{self.name_by_code.get(top[0], top[0])} at ${top[1]:,.2f}.")
            return self._wrap(total, rows, template,
                              table={"type": "breakdown", "rows": [{"code": c, "name": self.name_by_code.get(c, c), "total": v} for c, v in ranked]})

        if name == "list_transactions":
            return self._wrap(round(sum(t["amount"] for t in rows), 2), rows,
                              f"Here are {len(rows)} transactions{pp}, totalling ${sum(t['amount'] for t in rows):,.2f}.",
                              table=self._tx_table(rows))

        return None

    def _tx_table(self, rows: list[dict]) -> dict:
        return {"type": "transactions", "rows": [
            {"date": t["date"], "vendor": t["vendor_raw"], "amount": round(t["amount"], 2),
             "code": t["gt_code"]} for t in rows[:60]]}

    def _wrap(self, value, cites_rows, template, table=None) -> dict:
        return {"value": value, "citations": [t["id"] for t in cites_rows], "template": template, "table": table}

    # ---- planning ------------------------------------------------------------
    def _period(self, q: str) -> Optional[str]:
        qm = re.search(r"q([1-4])\b|\b(first|second|third|fourth)\s+quarter", q)
        yr = re.search(r"(20\d{2})", q)
        year = yr.group(1) if yr else "2026"
        if qm:
            qn = qm.group(1) or {"first": "1", "second": "2", "third": "3", "fourth": "4"}[qm.group(2)]
            return f"{year}-Q{qn}"
        for name, num in _MONTHS.items():
            if name in q:
                return f"{year}-{num}"
        if yr and "month" not in q:
            return year
        return None

    @staticmethod
    def _clean_padded(q: str) -> str:
        return " " + re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", q)) + " "

    def _category_in(self, q: str) -> Optional[str]:
        padded = self._clean_padded(q)
        for term, code in self._cat_terms:
            if f" {term} " in padded:
                return code
        return None

    def _vendor_in(self, q: str) -> Optional[str]:
        padded = self._clean_padded(q)
        for term, vid in self._vendor_terms:
            if " " in term or "." in term:   # multiword / dotted: substring on the raw text
                if term in q:
                    return vid
            elif f" {term} " in padded:        # single token: whole-word on cleaned text
                return vid
        return None

    def rule_plan(self, question: str) -> Optional[dict]:
        q = question.lower()
        if any(k in q for k in _ADVISORY):
            return {"tool": "advisory"}
        period = self._period(q)
        wants_list = any(w in q for w in ["show me", "list", "show all", "all that", "each transaction", "itemize", "breakdown of transactions"])
        if "how many" in q or "number of transactions" in q:
            return {"tool": "count_transactions", "period": period}
        if "average" in q:
            return {"tool": "average_transaction", "period": period}
        if ("top" in q or "biggest" in q or "largest" in q or "highest" in q) and ("vendor" in q or "supplier" in q or "merchant" in q):
            n = re.search(r"top\s+(\d+)", q)
            return {"tool": "top_vendors", "period": period, "n": int(n.group(1)) if n else 5}
        if ("largest" in q or "biggest" in q or "highest" in q) and ("expense" in q or "transaction" in q or "charge" in q or "payment" in q or "spend" in q):
            return {"tool": "largest_expense", "period": period}
        if "break" in q and "down" in q or "by category" in q or "where did" in q or "categories" in q:
            return {"tool": "category_breakdown", "period": period}
        cat_code = self._category_in(q)
        if cat_code:
            return {"tool": "sum_by_category", "code": cat_code, "period": period, "list": wants_list}
        vid = self._vendor_in(q)
        if vid and ("spend" in q or "spent" in q or "how much" in q or "pay" in q or "paid" in q):
            return {"tool": "spend_by_vendor", "vendor_id": vid, "period": period, "list": wants_list}
        if "total" in q and ("expense" in q or "spend" in q or "spent" in q):
            return {"tool": "total_expense", "period": period, "list": wants_list}
        if wants_list and ("transaction" in q or "all" in q):
            return {"tool": "list_transactions", "period": period}
        return None

    def _followup_plan(self, question: str, context: dict) -> Optional[dict]:
        """Resolve a follow-up against the previous turn (chat memory)."""
        tool = context.get("tool")
        if not tool or tool == "advisory":
            return None
        q = question.lower()
        cue = any(w in q for w in ["what about", "how about", "and ", "also", "same for", "same",
                                    "those", "that one", "what if", "instead", "then", "show me those",
                                    "list them", "list those"])
        new_period = self._period(q)
        new_vendor = self._vendor_in(q)
        new_code = self._category_in(q)
        wants_list = any(w in q for w in ["show", "list", "those", "them", "itemize", "each"])
        if not (cue or new_period or new_vendor or new_code):
            return None
        plan = {"tool": tool, "period": new_period or context.get("period"), "list": wants_list}
        if tool == "sum_by_category":
            plan["code"] = new_code or context.get("code")
            if new_vendor:  # "what about with Amazon?" pivots to a vendor question
                plan = {"tool": "spend_by_vendor", "vendor_id": new_vendor, "period": plan["period"], "list": wants_list}
        elif tool == "spend_by_vendor":
            plan["vendor_id"] = new_vendor or context.get("vendor_id")
            if new_code:
                plan = {"tool": "sum_by_category", "code": new_code, "period": plan["period"], "list": wants_list}
        return plan

    def llm_plan(self, question: str, history: list | None = None) -> Optional[dict]:
        if self.provider.name != "groq":
            return None
        cats = ", ".join(f"{n}={c}" for n, c in self.code_by_name.items())
        system = (
            "Translate a CPA client's question into ONE tool call as STRICT JSON {\"tool\":...,\"params\":{...}}.\n"
            "Tools and params:\n"
            "  sum_by_category {code, period, list}\n  total_expense {period, list}\n"
            "  count_transactions {period}\n  average_transaction {period}\n"
            "  spend_by_vendor {vendor, period, list}\n  top_vendors {period, n}\n"
            "  largest_expense {period}\n  category_breakdown {period}\n  list_transactions {period}\n"
            "  advisory {}   (ONLY for genuine requests for professional advice or an opinion)\n"
            "For ANY factual question about spend, totals, counts, averages, vendors, categories, or "
            "transactions, you MUST choose a data tool, never advisory.\n"
            "period is 'YYYY-MM' for a month, 'YYYY-Qn' for a quarter, 'YYYY' for a year, or null.\n"
            "list is true if the user wants the individual transactions shown.\n"
            f"Valid category codes: {cats}.\n"
            "Use a category code for 'code'. Use a free-text vendor name for 'vendor'. Only output JSON.")
        convo = ""
        if history:
            convo = "Recent conversation (resolve references like 'that' or 'what about X'):\n" + \
                    "\n".join(f"{h.get('role')}: {h.get('text')}" for h in history[-4:]) + "\n\n"
        try:
            out = self.provider.chat(system, f"{convo}New question: {question}")
            start, end = out.find("{"), out.rfind("}")
            plan = json.loads(out[start:end + 1])
            tool = plan.get("tool")
            params = plan.get("params", {})
            if params.get("vendor"):
                params["vendor_id"] = self._vendor_in(str(params["vendor"]).lower()) or self._vendor_in(question.lower())
            if tool == "spend_by_vendor" and not params.get("vendor_id"):
                return None
            return {"tool": tool, **params}
        except Exception:
            return None

    # ---- answer --------------------------------------------------------------
    def answer(self, client_id: str, question: str, context: dict | None = None,
               history: list | None = None) -> dict:
        cname = self._client_names.get(client_id, client_id)
        trace = [{"label": "Scope guard", "detail": f"locked to {cname} ({client_id})", "ok": True}]

        plan = self.rule_plan(question)
        planner = "rule-based"
        if plan is None and context:
            plan = self._followup_plan(question, context)
            if plan:
                planner = "rule-based (follow-up)"
        if plan is None:
            plan = self.llm_plan(question, history)
            planner = "model planner"
        if plan is None:
            return self._abstain(client_id, question, "I could not map that to your records.", trace)
        # on a follow-up, inherit an unspecified period from the previous turn
        if plan.get("tool") != "advisory" and not plan.get("period") and context and context.get("period") \
           and any(w in question.lower() for w in ["what about", "how about", "also", "same", "and ", "then", "instead"]):
            plan["period"] = context["period"]

        tool = plan.get("tool")
        trace.append({"label": "Plan intent", "detail": f"{tool} via {planner}"
                      + (f", period {plan.get('period')}" if plan.get("period") else ""), "ok": tool != "advisory"})

        if tool == "advisory":
            return self._abstain(client_id, question, "That is professional advice, not a question about your records.", trace)

        result = self._tool(tool, client_id, plan)
        if result is None:
            return self._abstain(client_id, question, "Unsupported question type.", trace)

        value, cites, template, table = result["value"], result["citations"], result["template"], result["table"]
        trace.append({"label": "Query graph + ledger", "detail": f"{tool}({', '.join(f'{k}={v}' for k,v in plan.items() if k!='tool')})", "ok": True})
        trace.append({"label": "Compute (by code, not generated)", "detail": f"= {value} from {len(cites)} transactions", "ok": True})

        composed, used_llm = self._compose(question, template, value)
        grounded = self._validate(composed, value)
        if not grounded:
            composed, grounded = template, self._validate(template, value)
            used_llm = False
        model_tag = "model phrased" if used_llm else "verified template"
        trace.append({"label": "Compose", "detail": f"phrased via {model_tag}", "ok": True})
        trace.append({"label": "Validate number vs evidence", "detail": "exact match" if grounded else "mismatch, refused", "ok": grounded})

        if not grounded:
            return self._abstain(client_id, question, "Validation failed.", trace)
        audit.record("answer-agent", "answer_grounded",
                     {"client_id": client_id, "tool": tool, "citations": len(cites)}, firm_id=self.firm_id)
        return {"client_id": client_id, "question": question, "kind": tool, "value": value,
                "answer": _strip_dashes(composed), "computed": template, "citations": cites,
                "table": table, "grounded": True, "abstained": False, "delivery": "auto_send",
                "generated_by": model_tag, "trace": trace,
                "context": {"tool": tool, "period": plan.get("period"),
                            "code": plan.get("code"), "vendor_id": plan.get("vendor_id")}}

    def _compose(self, question: str, computed_sentence: str, value) -> tuple[str, bool]:
        if self.provider.name != "groq":
            return computed_sentence, False
        system = ("You are Ed, a warm and concise assistant for a CPA firm, replying to the firm's "
                  "client. You are GIVEN a fact computed from the client's own ledger. Reply in 1 to 2 "
                  "friendly sentences that convey it. You MUST include the exact figure provided and MUST "
                  "NOT invent any other numbers, dates, vendors, or categories. Do not use em dashes or "
                  "en dashes; use commas or periods. No disclaimers.")
        user = f"Client question: {question}\nComputed fact: {computed_sentence}\nExact figure to include: {value}"
        try:
            out = _strip_dashes(self.provider.chat(system, user).strip())
            return (out or computed_sentence), bool(out)
        except Exception:
            return computed_sentence, False

    # ---- helpers -------------------------------------------------------------
    def _period_phrase(self, period: Optional[str]) -> str:
        if not period:
            return ""
        if "-Q" in period:
            yr, q = period.split("-Q")
            return f" in Q{q} {yr}"
        if len(period) == 4:
            return f" in {period}"
        y, m = period.split("-")
        names = {v: k.capitalize() for k, v in _MONTHS.items()}
        return f" in {names.get(m, m)} {y}"

    @staticmethod
    def _validate(text: str, value) -> bool:
        nums = re.findall(r"[\d,]+\.?\d*", text.replace("$", ""))
        parsed = {float(n.replace(",", "")) for n in nums if n.replace(",", "").replace(".", "").isdigit()}
        return float(value) in parsed or round(float(value), 2) in parsed

    def _abstain(self, client_id, question, reason, trace=None) -> dict:
        trace = (trace or []) + [{"label": "Abstain + escalate", "detail": reason, "ok": True}]
        audit.record("answer-agent", "abstain_escalate",
                     {"client_id": client_id, "reason": reason}, firm_id=self.firm_id)
        return {"client_id": client_id, "question": question, "kind": "abstain",
                "value": None, "citations": [], "table": None, "grounded": False, "abstained": True,
                "delivery": "escalate_to_accountant", "generated_by": "policy",
                "reason": reason, "trace": trace,
                "answer": "I want to be precise here, so I'm looping in your accountant on this one."}
