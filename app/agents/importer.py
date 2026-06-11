"""Light integration seam: import transactions from a CSV (a QuickBooks / bank-feed export) and code
them on the way in. This is the 'moving data between systems' pain: paste an export, get coded books.

Production swaps the CSV for a QuickBooks / Plaid connector behind the same function.
"""
from __future__ import annotations

import csv
import io

from .. import db
from . import code_agent
from ..trust import audit

SAMPLE_CSV = """date,description,amount
2026-02-03,AMZN Mktp US,212.45
2026-02-05,UBER *TRIP,28.90
2026-02-07,WEWORK 0567,1250.00
2026-02-09,GOOGLE *ADS,940.10
2026-02-11,STARBUCKS #1180,9.75
2026-02-14,UPWORK *FREELANCE,1800.00
"""


def import_csv(firm_id: str, client_id: str, csv_text: str) -> dict:
    rows = list(csv.DictReader(io.StringIO(csv_text.strip())))
    engs = db.get_engagements(firm_id, client_id)
    eng_id = engs[0]["id"] if engs else f"{client_id}-e0"
    txns = []
    for i, r in enumerate(rows):
        g = {k.lower(): v for k, v in r.items()}
        try:
            amt = float(str(g.get("amount", "0")).replace("$", "").replace(",", ""))
        except ValueError:
            amt = 0.0
        tid = f"{client_id}-import-{i}"
        txns.append({"id": tid, "firm_id": firm_id, "client_id": client_id, "engagement_id": eng_id,
                     "batch_id": "import", "date": g.get("date", "2026-02-01"),
                     "vendor_raw": g.get("description", "Imported"), "vendor_id": None,
                     "memo": "imported from CSV", "amount": amt,
                     "source_doc_id": "csv_import", "source_span": f"csv row {i+1}",
                     "gt_code": None, "is_anomaly": 0, "anomaly_type": None})
    if not txns:
        return {"imported": 0, "coded": []}
    db.insert_rows("transactions", txns)

    accounts = db.get_gl_accounts(firm_id)
    compiled, meta = code_agent.build_pipeline(firm_id, txns, accounts)
    coded = []
    for t in txns:
        c = code_agent.categorize_one(compiled, meta, firm_id, "import", t)
        coded.append({"vendor": t["vendor_raw"], "amount": t["amount"],
                      "code": c["predicted_code"], "account": c["predicted_account_name"],
                      "confidence": c["calibrated_confidence"], "status": c["status"]})
    audit.record("max-importer", "csv_import",
                 {"client_id": client_id, "rows": len(txns)}, firm_id=firm_id)
    return {"imported": len(txns), "coded": coded}
