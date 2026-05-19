from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from erpnext_client import ERPNextError, get_client


EXPECTED_ROLE_PROFILES = [
    "Baro Estimate Manager",
    "Baro Regular Client Manager",
    "Baro Production Manager",
    "Baro Technician",
    "Baro Supply",
    "Baro Accounting",
    "Baro Admin Owner",
]

EXPECTED_WORKFLOW_STATES = [
    "New",
    "Need Follow-up",
    "Diagnostics Offered",
    "Waiting Prepayment",
    "Diagnostics Paid",
    "Technician Assigned",
    "Diagnostics In Progress",
    "Diagnosis Completed",
    "Estimate Sent",
    "Waiting Client Approval",
    "Parts Needed",
    "Repair In Progress",
    "Repair Completed",
    "Invoice Sent",
    "Paid",
    "Warranty Active",
    "Closed",
    "Lost",
    "Spam",
    "Unrelated",
]


def check_doc(client, doctype: str, name: str) -> bool:
    try:
        client.get_doc(doctype, name)
        print(f"OK   {doctype}: {name}")
        return True
    except ERPNextError as exc:
        print(f"WARN {doctype}: {name} -> {exc}")
        return False


def main() -> int:
    client = get_client()
    failures = 0

    print("Checking Baro ERPNext MVP setup...")
    failures += int(not check_doc(client, "DocType", "Repair Job"))

    for profile in EXPECTED_ROLE_PROFILES:
        failures += int(not check_doc(client, "Role Profile", profile))

    for state in EXPECTED_WORKFLOW_STATES:
        failures += int(not check_doc(client, "Workflow State", state))

    failures += int(not check_doc(client, "Workflow", "Repair Job Workflow"))

    if failures:
        print(f"Verification finished with warnings/errors: {failures}")
        return 1

    print("Verification finished successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
