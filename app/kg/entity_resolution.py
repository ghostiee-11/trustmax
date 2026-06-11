"""Vendor entity resolution: map a noisy bank descriptor to a canonical vendor.

Bank lines look like "AMZN Mktp US*2Z3", "STARBUCKS #1234", "GOOGLE *ADS 8829". Resolving these to one
canonical Vendor is what makes coding, spend analytics, and the knowledge graph consistent.

Pipeline (explainable, CPU-only):
  normalize -> exact alias match -> fuzzy (rapidfuzz) -> semantic (embeddings) -> abstain.

Splink / Zingg / dedupe are the documented scale-out path (see docs/design-decisions.md); this
implementation is dependency-light and fully explainable, which is what a CPA needs.
"""
from __future__ import annotations

import re
from typing import Optional

import numpy as np
from rapidfuzz import fuzz, process

from .. import db
from ..memory import get_embedder

_STOP = {"inc", "llc", "co", "corp", "ltd", "the", "company", "intl", "us", "usa", "bill", "store"}
_FUZZY_THRESHOLD = 86.0
_EMBED_THRESHOLD = 0.62


def normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[*#@/\\]", " ", s)
    s = re.sub(r"\d+", " ", s)          # drop store/txn numbers
    s = re.sub(r"[^a-z\s]", " ", s)
    toks = [t for t in s.split() if t not in _STOP and len(t) > 1]
    return " ".join(toks).strip()


class Resolver:
    def __init__(self, firm_id: str):
        self.firm_id = firm_id
        vendors = db.get_vendors(firm_id)
        self.vendor_by_id = {v["id"]: v for v in vendors}
        # known aliases -> vendor_id (normalized)
        self.alias_index: dict[str, str] = {}
        for v in vendors:
            self.alias_index[normalize(v["canonical_name"])] = v["id"]
        for a in db.get_vendor_aliases(firm_id):
            key = normalize(a["alias"])
            if key:
                self.alias_index.setdefault(key, a["vendor_id"])
        self._alias_keys = list(self.alias_index.keys())
        # canonical embeddings for the semantic fallback
        self._emb = get_embedder()
        self._canon_ids = [v["id"] for v in vendors]
        self._canon_vecs = self._emb.embed([v["canonical_name"] for v in vendors]) if vendors else None

    def resolve(self, raw: str) -> dict:
        norm = normalize(raw)
        if not norm:
            return {"vendor_id": None, "confidence": 0.0, "method": "empty"}

        # 1) exact normalized alias
        if norm in self.alias_index:
            vid = self.alias_index[norm]
            return self._hit(vid, 1.0, "exact")

        # 2) fuzzy over known alias keys
        match = process.extractOne(norm, self._alias_keys, scorer=fuzz.token_set_ratio)
        if match and match[1] >= _FUZZY_THRESHOLD:
            vid = self.alias_index[match[0]]
            return self._hit(vid, round(match[1] / 100.0, 3), "fuzzy")

        # 3) semantic nearest canonical
        if self._canon_vecs is not None:
            q = self._emb.embed([raw])
            sims = (self._canon_vecs @ q[0])
            j = int(np.argmax(sims))
            if float(sims[j]) >= _EMBED_THRESHOLD:
                return self._hit(self._canon_ids[j], round(float(sims[j]), 3), "embedding")

        return {"vendor_id": None, "confidence": 0.0, "method": "abstain"}

    def _hit(self, vendor_id: str, conf: float, method: str) -> dict:
        v = self.vendor_by_id.get(vendor_id, {})
        return {"vendor_id": vendor_id, "canonical_name": v.get("canonical_name"),
                "default_code": v.get("default_code"), "confidence": conf, "method": method}


def _perturb(raw: str, rng) -> str:
    """Simulate unseen bank-descriptor variants so ER is not a trivial exact-match task."""
    s = raw
    if rng.random() < 0.5:
        s = s + f" #{rng.randint(100, 9999)}"
    if rng.random() < 0.4:
        s = s.upper()
    if rng.random() < 0.3:
        s = s.replace(" ", "  ")
    if rng.random() < 0.2 and len(s) > 6:
        s = s[: len(s) - 2]  # truncate
    return s


def evaluate(firm_id: str, perturb: bool = True) -> dict:
    """Resolve every transaction's vendor descriptor and score against the ground-truth vendor_id."""
    import random
    rng = random.Random(13)
    resolver = Resolver(firm_id)
    txns = [t for t in db.get_transactions(firm_id) if t.get("vendor_id")]
    correct = 0
    methods: dict[str, int] = {}
    for t in txns:
        raw = _perturb(t["vendor_raw"], rng) if perturb else t["vendor_raw"]
        res = resolver.resolve(raw)
        methods[res["method"]] = methods.get(res["method"], 0) + 1
        if res["vendor_id"] == t["vendor_id"]:
            correct += 1
    n = len(txns)
    return {"firm_id": firm_id, "n": n, "accuracy": round(correct / n, 4) if n else 0.0,
            "method_breakdown": methods}


if __name__ == "__main__":
    import json
    print(json.dumps(evaluate("firm00", perturb=True), indent=2))
