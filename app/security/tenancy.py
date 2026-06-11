"""Multi-tenant isolation. Every domain row is scoped by firm_id and the data layer filters on it;
this module adds an explicit guard so a request in one firm's context can never touch another firm's
data, and provides a context object the API threads through.
"""
from __future__ import annotations

from dataclasses import dataclass

from .. import db


class TenantIsolationError(Exception):
    pass


@dataclass
class TenantContext:
    firm_id: str
    user_role: str = "partner"
    user_id: str = "demo-user"


def assert_same_tenant(ctx: TenantContext, firm_id: str) -> None:
    if ctx.firm_id != firm_id:
        raise TenantIsolationError(
            f"cross-tenant access denied: context firm={ctx.firm_id} tried to access firm={firm_id}")


def get_transaction_scoped(ctx: TenantContext, transaction_id: str) -> dict:
    """Fetch a transaction only if it belongs to the caller's firm; otherwise deny."""
    tx = db.get_transaction(transaction_id)
    if tx is None:
        raise KeyError("transaction not found")
    assert_same_tenant(ctx, tx["firm_id"])
    return tx
