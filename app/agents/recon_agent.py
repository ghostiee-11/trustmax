"""Bank reconciliation agent.

Reconciliation is the single biggest time sink in a bookkeeping firm: matching the bank statement to
the general ledger line by line, then chasing down the handful that do not tie. Trustmax does the
matching deterministically (amount, date window, payee similarity), surfaces ONLY the exceptions, and
explains every match and every break, so a senior reviews minutes of exceptions instead of hours of
ticking and tying.

The bank statement is synthesized from the client's coded ledger for this demo (in production it is a
bank feed or an uploaded statement), with realistic breaks injected: timing differences, charges on
the statement that are not yet in the books, outstanding items in the books that have not cleared, and
amount mismatches. The matcher has no knowledge of which lines were planted.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from .. import db

_TOL = 0.005          # amount tolerance for a clean match (half a cent relative)
_DATE_WINDOW = 4      # days the bank can lag the book entry and still match


def _seed(*parts: str) -> int:
    return sum(ord(ch) for p in parts for ch in p)


def _shift(d: str, days: int) -> str:
    try:
        y, m, dd = (int(x) for x in d.split("-"))
        return (date(y, m, dd) + timedelta(days=days)).isoformat()
    except Exception:
        return d


def _book_entries(firm_id: str, client_id: str, period: str) -> list[dict]:
    rows = db.get_transactions(firm_id, batch_id=period, client_id=client_id)
    out = []
    for t in rows:
        if str(t["id"]).endswith("-dup"):
            continue  # duplicates are an anomaly concern, not a recon seed
        cat = db.get_categorization(t["id"]) or {}
        out.append({"id": t["id"], "date": t["date"], "vendor": t["vendor_raw"],
                    "amount": round(float(t["amount"]), 2), "code": cat.get("predicted_code") or t.get("gt_code")})
    return out


def _build_statement(book: list[dict], rng: random.Random) -> tuple[list[dict], dict]:
    """Synthesize bank lines from book entries with realistic breaks. Returns (lines, planted)."""
    lines: list[dict] = []
    planted = {"timing": 0, "in_bank_not_books": 0, "in_books_not_bank": 0, "amount_mismatch": 0}
    n = len(book)
    # indexes to perturb
    skip = set(rng.sample(range(n), k=min(max(1, n // 12), n))) if n else set()           # outstanding in books
    mismatch = set(rng.sample(range(n), k=min(max(1, n // 16), n))) if n else set()        # amount differs
    timing = set(rng.sample(range(n), k=min(max(1, n // 10), n))) if n else set()          # cleared a few days later

    for i, b in enumerate(book):
        if i in skip:
            planted["in_books_not_bank"] += 1
            continue  # outstanding: in the books, has not cleared the bank
        amt = b["amount"]
        bdate = b["date"]
        if i in mismatch:
            amt = round(amt + rng.choice([-1, 1]) * round(amt * rng.uniform(0.03, 0.12), 2), 2)
            planted["amount_mismatch"] += 1
        if i in timing:
            bdate = _shift(b["date"], rng.randint(3, 9))
            planted["timing"] += 1
        lines.append({"id": f"bank-{i}", "date": bdate, "payee": b["vendor"], "amount": amt})

    # charges on the statement not yet in the books (bank fees, autopay)
    for j in range(max(1, n // 14)):
        amt = round(rng.uniform(12, 240), 2)
        lines.append({"id": f"bank-extra-{j}", "date": _shift(book[0]["date"] if book else "2026-01-15", rng.randint(0, 20)),
                      "payee": rng.choice(["STRIPE FEE", "BANK SERVICE CHARGE", "AUTOPAY UTILITIES", "WIRE FEE", "ACH DEBIT"]),
                      "amount": amt})
        planted["in_bank_not_books"] += 1

    rng.shuffle(lines)
    return lines, planted


def _payee_match(a: str, b: str) -> bool:
    a, b = (a or "").lower(), (b or "").lower()
    if not a or not b:
        return False
    ta, tb = set(a.replace("*", " ").split()), set(b.replace("*", " ").split())
    return bool(ta & tb) or a[:5] == b[:5]


def reconcile(firm_id: str, client_id: str, period: str | None = None) -> dict:
    period = period or "2026-01"
    book = _book_entries(firm_id, client_id, period)
    if not book:
        return {"period": period, "summary": {"bank_lines": 0, "book_lines": 0, "matched": 0,
                "exceptions": 0, "match_rate": 0, "reconciled_amount": 0, "exceptions_amount": 0},
                "matches": [], "exceptions": []}

    rng = random.Random(_seed(client_id, period))
    lines, _planted = _build_statement(book, rng)

    book_left = {b["id"]: b for b in book}
    matches: list[dict] = []
    exceptions: list[dict] = []

    # 1) clean and timing matches: amount within tolerance, payee similar, date within window
    for ln in sorted(lines, key=lambda x: x["id"]):
        best = None
        for b in book_left.values():
            if abs(b["amount"] - ln["amount"]) <= max(_TOL * max(abs(b["amount"]), 1), 0.01) and _payee_match(b["vendor"], ln["payee"]):
                best = b
                break
        if best:
            try:
                gap = abs((date.fromisoformat(ln["date"]) - date.fromisoformat(best["date"])).days)
            except Exception:
                gap = 0
            timing = gap > _DATE_WINDOW
            matches.append({"bank": ln, "book": {"id": best["id"], "vendor": best["vendor"],
                            "amount": best["amount"], "code": best["code"]},
                            "confidence": round(0.99 - (0.1 if timing else 0), 2),
                            "why": (f"amount ${best['amount']:,.2f} ties, payee matches, cleared {gap} days later"
                                    if timing else f"amount ${best['amount']:,.2f} and payee match within the date window"),
                            "timing": timing})
            if timing:
                exceptions.append({"type": "timing", "amount": best["amount"],
                                   "detail": f"{best['vendor']} ${best['amount']:,.2f} cleared {gap} days after it was booked",
                                   "bank": ln, "book": {"id": best["id"], "vendor": best["vendor"], "amount": best["amount"]},
                                   "suggestion": "Timing difference. It clears next period; no action unless it never clears."})
            del book_left[best["id"]]
            ln["_used"] = True

    # 2) amount mismatches: payee matches a remaining book item but the amount is off
    for ln in lines:
        if ln.get("_used"):
            continue
        cand = None
        for b in book_left.values():
            if _payee_match(b["vendor"], ln["payee"]) and abs(b["amount"] - ln["amount"]) <= max(b["amount"] * 0.2, 1):
                cand = b
                break
        if cand:
            diff = round(ln["amount"] - cand["amount"], 2)
            exceptions.append({"type": "amount_mismatch", "amount": diff,
                               "detail": f"{cand['vendor']}: bank ${ln['amount']:,.2f} vs books ${cand['amount']:,.2f} (off ${abs(diff):,.2f})",
                               "bank": ln, "book": {"id": cand["id"], "vendor": cand["vendor"], "amount": cand["amount"]},
                               "suggestion": "Confirm the booked amount. Likely a tip, fee, or partial payment."})
            del book_left[cand["id"]]
            ln["_used"] = True

    # 3) on the statement, not in the books
    for ln in lines:
        if ln.get("_used"):
            continue
        exceptions.append({"type": "in_bank_not_books", "amount": ln["amount"],
                           "detail": f"{ln['payee']} ${ln['amount']:,.2f} on the statement has no matching ledger entry",
                           "bank": ln, "book": None,
                           "suggestion": "Record it. Often a bank fee or autopay that was never entered."})

    # 4) in the books, not yet on the statement (outstanding)
    for b in book_left.values():
        exceptions.append({"type": "in_books_not_bank", "amount": b["amount"],
                           "detail": f"{b['vendor']} ${b['amount']:,.2f} is booked but has not cleared the bank",
                           "bank": None, "book": {"id": b["id"], "vendor": b["vendor"], "amount": b["amount"]},
                           "suggestion": "Outstanding item. Carry it forward; follow up if it ages."})

    reconciled_amt = round(sum(m["book"]["amount"] for m in matches), 2)
    exc_amt = round(sum(abs(e["amount"]) for e in exceptions), 2)
    order = {"in_bank_not_books": 0, "amount_mismatch": 1, "in_books_not_bank": 2, "timing": 3}
    exceptions.sort(key=lambda e: order.get(e["type"], 9))

    return {
        "period": period,
        "summary": {"bank_lines": len(lines), "book_lines": len(book), "matched": len(matches),
                    "exceptions": len(exceptions),
                    "match_rate": round(len(matches) / max(len(lines), 1), 3),
                    "reconciled_amount": reconciled_amt, "exceptions_amount": exc_amt},
        "matches": matches[:40],
        "exceptions": exceptions,
    }
