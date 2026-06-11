"""Typed domain models shared across the agents, store, and API."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class Account(BaseModel):
    """A general-ledger account from the firm's chart of accounts."""
    code: str
    name: str
    description: str = ""


class Transaction(BaseModel):
    """A single bookkeeping line awaiting categorization. Carries source provenance."""
    id: str
    batch_id: str
    date: str
    vendor: str
    memo: str = ""
    amount: float
    source_doc_id: str
    source_span: str  # e.g. "bank_statement_2026_q1.csv:row 14" or "receipt_uber_0312.jpg"
    gt_code: Optional[str] = None  # ground-truth label (synthetic data only; never shown to the agent)


class RetrievedExample(BaseModel):
    """A past human-approved categorization pulled from firm memory as few-shot context."""
    vendor: str
    memo: str
    code: str
    account_name: str
    rationale: str
    similarity: float


class Categorization(BaseModel):
    """The multi-agent pipeline's decision for one transaction."""
    transaction_id: str
    batch_id: str
    predicted_code: str
    predicted_account_name: str
    raw_confidence: float          # categorizer's self-reported confidence
    calibrated_confidence: float   # after the learned calibrator + signals
    memory_support: float          # similarity of the best retrieved example (0 if none)
    anomaly_score: float           # statistical risk, 0..1 (higher = riskier)
    anomaly_flags: list[str] = Field(default_factory=list)
    verifier_agreed: Optional[bool] = None  # critic agent's verdict
    verifier_note: str = ""
    rationale: str = ""
    retrieved_example_ids: list[str] = Field(default_factory=list)
    provider: str = ""
    model: str = ""
    decision: Literal["auto_approve", "needs_review"] = "needs_review"
    # filled after human action
    status: Literal["pending", "auto_approved", "approved", "corrected"] = "pending"
    final_code: Optional[str] = None


class ApprovalAction(BaseModel):
    transaction_id: str
    action: Literal["approve", "correct"]
    corrected_code: Optional[str] = None  # required when action == "correct"
    approver: str = "demo-cpa"


class MemoryItem(BaseModel):
    """A learned firm convention: an approved (vendor, memo) -> GL code mapping."""
    id: str
    vendor: str
    memo: str
    code: str
    account_name: str
    rationale: str
    source_transaction_id: str


class ClientMessageDraft(BaseModel):
    """Ed's approval-gated client-facing message for an ambiguous/missing item."""
    id: str
    transaction_id: str
    subject: str
    body: str
    status: Literal["pending", "approved", "sent"] = "pending"
