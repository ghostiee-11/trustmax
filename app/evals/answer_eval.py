"""Grounded Q&A eval. The headline trust metrics:
  - numeric_accuracy   computed answers that exactly match ground truth
  - groundedness       answered questions that carry citations (never an uncited number)
  - correct_abstention advisory/out-of-scope questions that correctly abstain
  - fabrication_rate   answers with a number not backed by a tool computation (must be 0)

Run: `python -m app.evals.answer_eval --firm firm00`
"""
from __future__ import annotations

import argparse
import json

from .. import db
from ..agents.answer_agent import AnswerAgent


def evaluate(firm_id: str) -> dict:
    agent = AnswerAgent(firm_id)
    qa = db.get_qa_pairs(firm_id)
    numeric_total = numeric_ok = 0
    grounded_answered = answered = 0
    abstain_total = abstain_ok = 0
    fabrications = 0

    for item in qa:
        gt = item["answer"]
        res = agent.answer(item["client_id"], item["question"])

        if gt.get("abstain"):
            abstain_total += 1
            if res["abstained"]:
                abstain_ok += 1
            continue

        # computed question
        if res["grounded"]:
            answered += 1
            if res["citations"]:
                grounded_answered += 1
            numeric_total += 1
            if abs(float(res["value"]) - float(gt["value"])) < 0.01:
                numeric_ok += 1
            if not res["citations"]:
                fabrications += 1  # a number with no evidence
        else:
            # abstained on a computable question (missed), counts against numeric coverage
            numeric_total += 1

    return {
        "firm_id": firm_id, "qa_pairs": len(qa),
        "numeric_accuracy": round(numeric_ok / numeric_total, 4) if numeric_total else 0.0,
        "groundedness": round(grounded_answered / answered, 4) if answered else 0.0,
        "correct_abstention": round(abstain_ok / abstain_total, 4) if abstain_total else 0.0,
        "fabrication_rate": round(fabrications / answered, 4) if answered else 0.0,
        "answered": answered, "abstained_correctly": abstain_ok,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--firm", default="firm00")
    args = ap.parse_args()
    print(json.dumps(evaluate(args.firm), indent=2))


if __name__ == "__main__":
    main()
