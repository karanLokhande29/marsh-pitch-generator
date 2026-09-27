"""Export the audit report to Excel / JSON."""
import json
from pathlib import Path

import pandas as pd


def audit_rows(audit: dict) -> list[dict]:
    rows = []
    for c in audit["claims"]:
        ev = c["evidence"][0] if c.get("evidence") else {}
        rows.append({"Claim ID": c["claim_id"], "Slide": c["slide_no"], "Claim": c["text"], "Type": c["kind"],
                     "Verdict": c["verdict"], "Flags": ", ".join(c.get("flags", [])),
                     "Source clause": ev.get("clause_id", ""), "Document": ev.get("doc", ""),
                     "Page": ev.get("page", ""), "Source text": ev.get("text", ""),
                     "Reason": c.get("reason", ""), "Suggested fix": c.get("suggested_fix", ""),
                     "Advisor action": c.get("advisor_action", "pending")})
    return rows


def export_audit(audit: dict, xlsx_path: Path, json_path: Path, decision: dict | None = None):
    summ = dict(audit["summary"])
    summ.update({"method": audit["method"], "audited_at": audit["audited_at"],
                 "policy_docs": "; ".join(audit["policy_docs"])})
    if decision:
        summ.update({f"decision_{k}": v for k, v in decision.items()})
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as xw:
        pd.DataFrame([summ]).T.reset_index().rename(columns={"index": "Metric", 0: "Value"}).to_excel(
            xw, sheet_name="Summary", index=False)
        df = pd.DataFrame(audit_rows(audit))
        df.to_excel(xw, sheet_name="Claim traceability", index=False)
        ws = xw.sheets["Claim traceability"]
        for col, w in zip("ABCDEFGHIJKLM", (14, 6, 60, 9, 14, 30, 22, 30, 6, 70, 45, 45, 14)):
            ws.column_dimensions[col].width = w
    Path(json_path).write_text(json.dumps({**audit, "decision": decision}, indent=2, default=str))
