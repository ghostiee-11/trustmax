"""Generate a large, realistic, fully-labeled synthetic accounting corpus.

Deterministic (seeded) so eval numbers are reproducible. Writes directly into the relational store.
Run: `python -m app.datagen.generate --scale demo`
"""
from __future__ import annotations

import argparse
import math
import random

from faker import Faker

from .. import db
from ..config import DATA_SCALE
from . import seeds

YEAR = 2026


def _slugify(name: str) -> str:
    keep = "".join(ch.lower() if ch.isalnum() else " " for ch in name)
    return "".join(keep.split()[:2]) or "client"


class Generator:
    def __init__(self, scale: str, seed: int = 7):
        self.cfg = seeds.SCALE_TIERS.get(scale, seeds.SCALE_TIERS["demo"])
        self.rng = random.Random(seed)
        self.fake = Faker()
        self.fake.seed_instance(seed)
        self.rows: dict[str, list[dict]] = {t: [] for t in
            ["firms", "employees", "clients", "engagements", "gl_accounts", "vendors",
             "vendor_aliases", "transactions", "documents", "qa_pairs"]}

    # ---- helpers
    def _ein(self) -> str:
        return f"{self.rng.randint(10,99)}-{self.rng.randint(1000000,9999999)}"

    def _amount(self, lo: float, hi: float, month: int) -> float:
        mid = (lo + hi) / 2
        # log-normal around the midpoint (Benford-ish skew), then seasonal weighting
        val = self.rng.lognormvariate(math.log(max(mid, 1)), 0.45)
        val = max(lo * 0.6, min(val, hi * 1.6))
        return round(val * seeds.SEASONAL_INDEX[month], 2)

    # ---- build
    def generate(self) -> dict:
        c = self.cfg
        for fi in range(c["firms"]):
            self._firm(fi)
        for t, rows in self.rows.items():
            db.insert_rows(t, rows)
        return {t: len(r) for t, r in self.rows.items()}

    def _firm(self, fi: int) -> None:
        firm_id = f"firm{fi:02d}"
        firm_name = self.fake.company() + " CPAs"
        self.rows["firms"].append({"id": firm_id, "name": firm_name, "slug": _slugify(firm_name)})

        for role in seeds.ROLES:
            self.rows["employees"].append({
                "id": f"{firm_id}-{role}", "firm_id": firm_id, "name": self.fake.name(),
                "role": role, "email": f"{role}@{_slugify(firm_name)}.cpa"})

        # chart of accounts (per firm)
        for code, name, typ, desc in seeds.CHART_OF_ACCOUNTS:
            self.rows["gl_accounts"].append({
                "id": f"{firm_id}-{code}", "firm_id": firm_id, "code": code,
                "name": name, "type": typ, "description": desc})

        # vendors + aliases (per firm), plus idiosyncratic GL overrides (what the flywheel learns)
        firm_vendors = []
        override_targets = self.rng.sample(seeds.VENDOR_CATALOG, k=min(5, len(seeds.VENDOR_CATALOG)))
        overrides = {}
        for v in override_targets:
            alt = self.rng.choice([c for c in seeds.EXPENSE_CODES if c != v[1]])
            overrides[v[0]] = alt
        for vi, (canon, default_gl, cat, mcc, aliases, amt) in enumerate(seeds.VENDOR_CATALOG):
            vid = f"{firm_id}-v{vi:02d}"
            gl = overrides.get(canon, default_gl)
            self.rows["vendors"].append({
                "id": vid, "firm_id": firm_id, "canonical_name": canon, "mcc": mcc,
                "category": cat, "default_code": gl})
            self.rows["vendor_aliases"].append({
                "id": f"{vid}-a0", "firm_id": firm_id, "vendor_id": vid, "alias": canon})
            for ai, al in enumerate(aliases):
                self.rows["vendor_aliases"].append({
                    "id": f"{vid}-a{ai+1}", "firm_id": firm_id, "vendor_id": vid, "alias": al})
            firm_vendors.append({"id": vid, "canon": canon, "gl": gl, "aliases": [canon] + aliases, "amt": amt})

        # clients + engagements + transactions + documents + qa
        for ci in range(self.cfg["clients"]):
            self._client(firm_id, ci, firm_vendors)

    def _client(self, firm_id: str, ci: int, firm_vendors: list[dict]) -> None:
        client_id = f"{firm_id}-c{ci:02d}"
        cname = self.fake.company()
        domain = f"{_slugify(cname)}.com"
        ein = self._ein()
        last4 = f"{self.rng.randint(0,9999):04d}"
        industry = self.rng.choice(seeds.CLIENT_INDUSTRIES)
        self.rows["clients"].append({
            "id": client_id, "firm_id": firm_id, "name": cname, "industry": industry,
            "ein": ein, "email_domain": domain, "bank_last4": last4})

        eng_type = self.rng.choice(["Bookkeeping", "Tax", "Audit"])
        eng_id = f"{client_id}-e0"
        self.rows["engagements"].append({
            "id": eng_id, "firm_id": firm_id, "client_id": client_id, "type": eng_type,
            "period": f"{YEAR}", "status": "active"})

        client_txns: list[dict] = []
        for m in range(self.cfg["months"]):
            month = 1 + m
            batch_id = f"{YEAR}-{month:02d}"
            n = self.cfg["txns"]
            for k in range(n):
                v = self.rng.choice(firm_vendors)
                raw = self.rng.choice(v["aliases"])
                amount = self._amount(v["amt"][0], v["amt"][1], month)
                tid = f"{client_id}-{batch_id}-{k:03d}"
                day = self.rng.randint(1, 27)
                client_txns.append({
                    "id": tid, "firm_id": firm_id, "client_id": client_id, "engagement_id": eng_id,
                    "batch_id": batch_id, "date": f"{YEAR}-{month:02d}-{day:02d}",
                    "vendor_raw": raw, "vendor_id": v["id"], "memo": f"{v['canon']} {self.rng.choice(['', 'recurring', 'client visit', 'monthly'])}".strip(),
                    "amount": amount, "source_doc_id": f"bank_{client_id}_{batch_id}.csv",
                    "source_span": f"bank_{client_id}_{batch_id}.csv:row {k+1}",
                    "gt_code": v["gl"], "is_anomaly": 0, "anomaly_type": None})

        self._inject_anomalies(firm_id, client_id, client_txns)
        self.rows["transactions"].extend(client_txns)
        self._documents(firm_id, client_id, domain, ein, last4, firm_vendors)
        self._qa(firm_id, client_id, cname, client_txns)

    def _inject_anomalies(self, firm_id: str, client_id: str, txns: list[dict]) -> None:
        if len(txns) < 10:
            return
        # duplicates (~1.5%)
        for _ in range(max(1, len(txns) // 70)):
            base = self.rng.choice(txns)
            dup = dict(base)
            dup["id"] = base["id"] + "-dup"
            dup["is_anomaly"] = 1
            dup["anomaly_type"] = "duplicate"
            txns.append(dup)
        # unusual amounts (~1.5%)
        for t in self.rng.sample(txns, k=max(1, len(txns) // 70)):
            t["amount"] = round(t["amount"] * self.rng.uniform(8, 16), 2)
            t["is_anomaly"] = 1
            t["anomaly_type"] = "unusual_amount"
        # missing categories: unknown vendor -> 6900 (~1%)
        for i in range(max(1, len(txns) // 100)):
            month = self.rng.randint(1, self.cfg["months"])
            tid = f"{client_id}-misc-{i}"
            txns.append({
                "id": tid, "firm_id": firm_id, "client_id": client_id,
                "engagement_id": f"{client_id}-e0", "batch_id": f"{YEAR}-{month:02d}",
                "date": f"{YEAR}-{month:02d}-15", "vendor_raw": self.fake.company(),
                "vendor_id": None, "memo": "unclear charge", "amount": round(self.rng.uniform(30, 900), 2),
                "source_doc_id": "manual", "source_span": "manual",
                "gt_code": "6900", "is_anomaly": 1, "anomaly_type": "missing_category"})

    def _documents(self, firm_id: str, client_id: str, domain: str, ein: str,
                   last4: str, firm_vendors: list[dict]) -> None:
        n_docs = self.cfg.get("docs", max(3, self.cfg["months"] * 2))
        for d in range(n_docs):
            v = self.rng.choice(firm_vendors)
            # vary signal strength: some docs are "hard" (weak signals) to exercise graph routing
            strength = self.rng.random()
            doc_type = self.rng.choice(["invoice", "receipt", "bank_statement", "tax_form", "engagement_letter"])
            mo = self.rng.randint(1, self.cfg["months"])
            self.rows["documents"].append({
                "id": f"{client_id}-doc{d:02d}", "firm_id": firm_id, "doc_type": doc_type,
                "filename": f"{doc_type}_{v['canon'].split()[0].lower()}_{d}.pdf",
                "sender_email": (f"ap@{domain}" if strength > 0.4 else self.fake.free_email()),
                "sender_domain": (domain if strength > 0.4 else self.fake.free_email().split("@")[-1]),
                "ein_hint": (ein if strength > 0.7 else None),
                "account_last4": (last4 if strength > 0.55 else None),
                "vendor_hint": v["canon"],
                "amount": round(self.rng.uniform(v["amt"][0], v["amt"][1]), 2),
                "doc_date": f"{YEAR}-{mo:02d}-{self.rng.randint(1,27):02d}",
                "gt_client_id": client_id, "routed_client_id": None,
                "routing_status": "pending", "routing_confidence": None,
                "received_at": f"{YEAR}-{mo:02d}-{self.rng.randint(1,27):02d}"})

    def _qa(self, firm_id: str, client_id: str, cname: str, txns: list[dict]) -> None:
        period = f"{YEAR}-01"
        in_period = [t for t in txns if t["batch_id"] == period and not t["is_anomaly"]]
        if not in_period:
            return
        # sum by a category
        cat_code = "6300"
        total_sw = round(sum(t["amount"] for t in in_period if t["gt_code"] == cat_code), 2)
        self.rows["qa_pairs"].append({
            "id": f"{client_id}-qa0", "firm_id": firm_id, "client_id": client_id,
            "question": f"How much did we spend on Software Subscriptions in January {YEAR}?",
            "kind": "sum_by_category",
            "answer": _json({"value": total_sw, "code": cat_code, "period": period})})
        # total expenses
        total = round(sum(t["amount"] for t in in_period), 2)
        self.rows["qa_pairs"].append({
            "id": f"{client_id}-qa1", "firm_id": firm_id, "client_id": client_id,
            "question": f"What were our total expenses in January {YEAR}?",
            "kind": "total_expense", "answer": _json({"value": total, "period": period})})
        # count
        self.rows["qa_pairs"].append({
            "id": f"{client_id}-qa2", "firm_id": firm_id, "client_id": client_id,
            "question": f"How many transactions did we have in January {YEAR}?",
            "kind": "count", "answer": _json({"value": len(in_period), "period": period})})
        # advisory / out-of-scope -> must abstain
        self.rows["qa_pairs"].append({
            "id": f"{client_id}-qa3", "firm_id": firm_id, "client_id": client_id,
            "question": "Should I convert my LLC to an S-corp to save on taxes?",
            "kind": "advisory", "answer": _json({"abstain": True})})


def _json(obj) -> str:
    import json
    return json.dumps(obj)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default=DATA_SCALE, choices=list(seeds.SCALE_TIERS))
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    db.reset_db()
    gen = Generator(args.scale, seed=args.seed)
    counts = gen.generate()
    print(f"Generated synthetic corpus (scale={args.scale}):")
    for t, n in counts.items():
        print(f"  {t:16s} {n:,}")


if __name__ == "__main__":
    main()
