"""Per-tenant field encryption for PII (client EIN, bank account).

Envelope model: a master key (here from config; in production from a KMS/HSM) derives a unique data
key per firm. Encrypting at the field level means a single leaked row is useless without that firm's
key, and one firm's key never decrypts another firm's data (cryptographic isolation).

Uses cryptography.Fernet (AES-128-CBC + HMAC) when available; otherwise a clearly-labelled
HMAC-keystream fallback so the demo runs with no extra dependency. Production note in docs/security.md.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

from ..config import MASTER_ENCRYPTION_KEY

try:
    from cryptography.fernet import Fernet
    _HAVE_FERNET = True
except Exception:  # pragma: no cover
    _HAVE_FERNET = False


def _firm_key_bytes(firm_id: str) -> bytes:
    # HKDF-like derivation: per-tenant data key from the master key + firm id.
    return hashlib.sha256(f"{MASTER_ENCRYPTION_KEY}:{firm_id}".encode()).digest()


def _fernet(firm_id: str):
    return Fernet(base64.urlsafe_b64encode(_firm_key_bytes(firm_id)))


def encrypt_field(firm_id: str, plaintext: str) -> str:
    if plaintext is None:
        return None
    if _HAVE_FERNET:
        return "f:" + _fernet(firm_id).encrypt(plaintext.encode()).decode()
    # fallback: HMAC-CTR keystream XOR + tag (demo-grade, not for production)
    key = _firm_key_bytes(firm_id)
    nonce = os.urandom(8)
    stream = b"".join(hmac.new(key, nonce + i.to_bytes(4, "big"), hashlib.sha256).digest()
                      for i in range((len(plaintext) // 32) + 1))
    ct = bytes(b ^ s for b, s in zip(plaintext.encode(), stream))
    tag = hmac.new(key, nonce + ct, hashlib.sha256).digest()[:16]
    return "h:" + base64.urlsafe_b64encode(nonce + tag + ct).decode()


def decrypt_field(firm_id: str, token: str) -> str:
    if token is None:
        return None
    if token.startswith("f:"):
        return _fernet(firm_id).decrypt(token[2:].encode()).decode()
    if token.startswith("h:"):
        raw = base64.urlsafe_b64decode(token[2:])
        nonce, tag, ct = raw[:8], raw[8:24], raw[24:]
        key = _firm_key_bytes(firm_id)
        if not hmac.compare_digest(tag, hmac.new(key, nonce + ct, hashlib.sha256).digest()[:16]):
            raise ValueError("auth tag mismatch (wrong firm key or tampered ciphertext)")
        stream = b"".join(hmac.new(key, nonce + i.to_bytes(4, "big"), hashlib.sha256).digest()
                          for i in range((len(ct) // 32) + 1))
        return bytes(b ^ s for b, s in zip(ct, stream)).decode()
    raise ValueError("unknown ciphertext format")
