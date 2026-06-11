"""Security demonstration: tenant isolation, RBAC least-privilege, and per-tenant field encryption.

Run: `python -m app.evals.security_eval`
"""
from __future__ import annotations

from .. import db
from ..security import crypto, rbac
from ..security.tenancy import TenantContext, TenantIsolationError, get_transaction_scoped


def run() -> dict:
    results = {}

    # 1) Tenant isolation: firm00 context must not read firm01's transaction.
    firms = db.get_firms()
    f0, f1 = firms[0]["id"], firms[1]["id"]
    other_tx = db.get_transactions(f1)[0]["id"]
    ctx = TenantContext(firm_id=f0, user_role="partner")
    try:
        get_transaction_scoped(ctx, other_tx)
        results["tenant_isolation"] = "FAIL (cross-tenant read allowed)"
    except TenantIsolationError:
        results["tenant_isolation"] = "PASS (cross-tenant read denied)"
    own_tx = db.get_transactions(f0)[0]["id"]
    results["same_tenant_read"] = "PASS" if get_transaction_scoped(ctx, own_tx) else "FAIL"

    # 2) RBAC: associate cannot export the audit trail; partner can.
    results["rbac_associate_export"] = "PASS (denied)" if not rbac.can("associate", "export_audit") else "FAIL"
    results["rbac_partner_export"] = "PASS (allowed)" if rbac.can("partner", "export_audit") else "FAIL"
    results["rbac_associate_can_approve"] = "PASS" if rbac.can("associate", "approve") else "FAIL"

    # 3) Per-tenant field encryption of PII (client EIN).
    client = db.get_clients(f0)[0]
    ein = client["ein"]
    token = crypto.encrypt_field(f0, ein)
    results["encryption_ciphertext_differs"] = "PASS" if token != ein and ein not in token else "FAIL"
    results["encryption_roundtrip"] = "PASS" if crypto.decrypt_field(f0, token) == ein else "FAIL"
    try:
        crypto.decrypt_field(f1, token)  # wrong firm's key must fail
        results["encryption_cross_tenant_decrypt"] = "FAIL (other firm decrypted it)"
    except Exception:
        results["encryption_cross_tenant_decrypt"] = "PASS (other firm's key cannot decrypt)"

    results["fernet_backend"] = crypto._HAVE_FERNET
    return results


def main() -> None:
    res = run()
    print("Security checks:")
    for k, v in res.items():
        print(f"  {k:36s} {v}")


if __name__ == "__main__":
    main()
