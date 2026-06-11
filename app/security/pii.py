"""PII / data-leak guard. Scans text (especially anything client-facing from Ed) for sensitive
identifiers and redacts them before it can be sent. Trust depends on never leaking a client's SSN.
"""
from __future__ import annotations

import re

_PATTERNS = [
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("ein", re.compile(r"\b\d{2}-\d{7}\b")),
    ("credit_card", re.compile(r"\b(?:\d[ -]?){15,16}\b")),
    ("bank_account", re.compile(r"\b\d{8,17}\b")),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
]


def scan(text: str) -> list[dict]:
    """Return a list of {type, match} for any PII found."""
    findings = []
    for kind, rx in _PATTERNS:
        for m in rx.finditer(text or ""):
            findings.append({"type": kind, "match": m.group(0)})
    return findings


def _mask(value: str) -> str:
    digits = [c for c in value if c.isdigit()]
    tail = "".join(digits[-4:]) if len(digits) >= 4 else ""
    return f"••••{tail}" if tail else "[REDACTED]"


def redact(text: str) -> tuple[str, list[dict]]:
    """Return (redacted_text, findings)."""
    findings = scan(text)
    out = text or ""
    for kind, rx in _PATTERNS:
        out = rx.sub(lambda m: f"[{kind.upper()} {_mask(m.group(0))}]", out)
    return out, findings


def guard(text: str) -> dict:
    """Decision for a client-facing message: block if PII present, with a redacted version."""
    redacted, findings = redact(text)
    return {"clean": not findings, "findings": findings, "redacted": redacted,
            "decision": "send" if not findings else "blocked_pending_redaction"}
