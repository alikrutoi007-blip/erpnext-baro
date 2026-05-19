from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from erpnext_client import ERPNextError, get_client


DOCTYPES = [
    "Customer",
    "Contact",
    "Address",
    "Lead",
    "Issue",
    "Maintenance Visit",
    "Call Log",
    "Employee",
    "Timesheet",
    "Item",
    "Sales Invoice",
    "Payment Entry",
    "Workflow",
    "Role Profile",
    "DocType",
]


def main() -> int:
    client = get_client()
    print("Checking standard DocTypes and API visibility...")
    failures = 0
    for doctype in DOCTYPES:
        try:
            docs = client.list_docs(doctype, fields=["name"], limit=1)
            print(f"OK   {doctype}: visible ({len(docs)} sample rows)")
        except ERPNextError as exc:
            failures += 1
            print(f"WARN {doctype}: {exc}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())