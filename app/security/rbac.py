"""Role-based access control. CPA firms need least-privilege: not everyone can send to clients or
export the audit trail. Permissions are checked at the API boundary and demonstrated in the eval.
"""
from __future__ import annotations

ROLE_PERMISSIONS = {
    "partner":   {"view", "approve", "correct", "route", "send_message", "export_audit", "manage"},
    "manager":   {"view", "approve", "correct", "route", "send_message", "export_audit"},
    "associate": {"view", "approve", "correct", "route"},
    "admin":     {"view", "manage", "export_audit"},
}


class PermissionError(Exception):
    pass


def can(role: str, action: str) -> bool:
    return action in ROLE_PERMISSIONS.get(role, set())


def require(role: str, action: str) -> None:
    if not can(role, action):
        raise PermissionError(f"role '{role}' is not permitted to '{action}'")
