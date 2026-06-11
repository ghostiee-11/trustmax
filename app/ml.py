"""Advanced ML layer: anomaly detection + learned confidence calibration.

These are the pieces that make the autonomy decision trustworthy:
  - AnomalyDetector: statistical risk per transaction (IsolationForest over amounts + duplicate /
    round-number / z-score heuristics). Risk lowers confidence and can force human review.
  - Calibrator: maps raw signals (model confidence, memory support, verifier agreement, anomaly) to a
    calibrated P(correct). Cold-start uses a transparent heuristic; once enough human-labeled
    approvals exist it fits a LogisticRegression on real outcomes. So calibration itself improves as
    the flywheel turns, which is the whole point.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from . import db

MIN_TRAIN = 14  # labeled approvals needed before the learned calibrator switches on


# ----------------------------------------------------------------- anomaly detection
class AnomalyDetector:
    def __init__(self, transactions: list[dict]) -> None:
        self._by_amount = [t["amount"] for t in transactions]
        self._seen: dict[tuple, int] = {}
        for t in transactions:
            key = ((t.get("vendor_raw") or t.get("vendor") or "").lower(), round(t["amount"], 2))
            self._seen[key] = self._seen.get(key, 0) + 1
        self._iso = None
        self._amounts_log = None
        if len(self._by_amount) >= 8:
            try:
                from sklearn.ensemble import IsolationForest
                self._amounts_log = np.array([[math.log1p(a)] for a in self._by_amount])
                self._iso = IsolationForest(random_state=7, contamination="auto").fit(self._amounts_log)
            except Exception:
                self._iso = None
        arr = np.array(self._by_amount) if self._by_amount else np.array([0.0])
        self._mean = float(arr.mean())
        self._std = float(arr.std()) or 1.0

    def score(self, tx: dict) -> tuple[float, list[str]]:
        flags: list[str] = []
        amount = tx["amount"]

        z = abs(amount - self._mean) / self._std
        if z > 2.5:
            flags.append("unusual_amount")

        if amount >= 500 and round(amount) % 100 == 0:
            flags.append("round_number")

        if self._seen.get(((tx.get("vendor_raw") or tx.get("vendor") or "").lower(), round(amount, 2)), 0) > 1:
            flags.append("possible_duplicate")

        iso_risk = 0.0
        if self._iso is not None:
            # decision_function: >0 = inlier (normal), <0 = outlier. Only outliers carry risk.
            d = float(self._iso.decision_function([[math.log1p(amount)]])[0])
            if d < 0:
                iso_risk = float(np.clip(-d * 2.5, 0.0, 1.0))

        heuristic_risk = min(1.0, 0.3 * len(flags) + min(z / 8.0, 0.3))
        risk = float(np.clip(0.6 * heuristic_risk + 0.4 * iso_risk, 0.0, 1.0))
        return risk, flags


# ----------------------------------------------------------------- calibration
def _feature_vec(raw_conf: float, memory_support: float, verifier_agreed: Optional[bool],
                 anomaly: float) -> list[float]:
    va = 1.0 if verifier_agreed in (True, None) else 0.0
    return [float(raw_conf), float(memory_support), va, float(anomaly)]


def _heuristic(raw_conf: float, memory_support: float, verifier_agreed: Optional[bool],
               anomaly: float) -> float:
    c = raw_conf
    if memory_support >= 0.7:
        c = max(c, 0.9)
    elif memory_support >= 0.55:
        c = max(c, 0.8)
    if verifier_agreed is False:
        c *= 0.5
    c *= (1.0 - 0.45 * anomaly)
    return float(np.clip(c, 0.02, 0.985))


def heuristic_calibrate(raw_conf: float, graph_support: float, verifier_agreed: Optional[bool],
                        anomaly: float) -> float:
    """Public calibration combiner used by the agents (graph support replaces memory support)."""
    return _heuristic(raw_conf, graph_support, verifier_agreed, anomaly)


class Calibrator:
    """Confidence calibrator that learns from accumulated human approvals."""

    def __init__(self) -> None:
        self._model = None
        self._trained_on = 0

    def fit_from_db(self, firm_id: str) -> None:
        # Train ONLY on human-reviewed items. Auto-approved items have final_code == predicted_code by
        # construction, so including them would leak a trivially-correct label and inflate confidence.
        cats = [c for c in db.get_categorizations(firm_id)
                if c.get("status") in ("approved", "corrected") and c.get("final_code")]
        X, y = [], []
        for c in cats:
            X.append(_feature_vec(c.get("raw_confidence", 0.5), c.get("memory_support", 0.0),
                                  c.get("verifier_agreed"), c.get("anomaly_score", 0.0)))
            # label: did the agent's prediction match the human's final decision?
            y.append(1 if c.get("predicted_code") == c.get("final_code") else 0)
        self._trained_on = len(y)
        if len(y) >= MIN_TRAIN and len(set(y)) == 2:
            try:
                from sklearn.linear_model import LogisticRegression
                self._model = LogisticRegression(class_weight="balanced", max_iter=500).fit(np.array(X), np.array(y))
            except Exception:
                self._model = None
        else:
            self._model = None

    @property
    def mode(self) -> str:
        return f"learned (n={self._trained_on})" if self._model is not None else f"heuristic (n={self._trained_on})"

    def calibrate(self, raw_conf: float, memory_support: float, verifier_agreed: Optional[bool],
                  anomaly: float) -> float:
        if self._model is not None:
            x = np.array([_feature_vec(raw_conf, memory_support, verifier_agreed, anomaly)])
            p = float(self._model.predict_proba(x)[0, 1])
            # blend a touch of the heuristic so a tiny training set can't produce wild extremes
            h = _heuristic(raw_conf, memory_support, verifier_agreed, anomaly)
            return float(np.clip(0.8 * p + 0.2 * h, 0.02, 0.99))
        return _heuristic(raw_conf, memory_support, verifier_agreed, anomaly)
