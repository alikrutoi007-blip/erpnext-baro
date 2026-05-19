from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from erpnext_client import ERPNextClient, ERPNextConfig


EXPECTED_WORKSPACE = "Baro CRM Demo"
EXPECTED_KANBAN = "Baro Repair Job Pipeline"
EXPECTED_NUMBER_CARDS = [
    "Baro Open Repair Jobs",
    "Baro Needs Follow-up",
    "Baro Active Repairs",
]
EXPECTED_ITEMS = [
    "DEMO-DIAGNOSTIC-SERVICE",
    "DEMO-REPAIR-LABOR",
    "DEMO-PARTS",
]
EXPECTED_EMPLOYEES = [
    "DEMO - Omar Technician",
    "DEMO - Diego Technician",
    "DEMO - Lena Dispatcher",
]
EXPECTED_REPAIR_STATUSES = {
    "DEMO-BARO-001": "Diagnostics Offered",
    "DEMO-BARO-002": "Waiting Prepayment",
    "DEMO-BARO-003": "Technician Assigned",
    "DEMO-BARO-004": "Estimate Sent",
    "DEMO-BARO-005": "Parts Needed",
    "DEMO-BARO-006": "Repair In Progress",
    "DEMO-BARO-007": "Paid",
    "DEMO-BARO-008": "Warranty Active",
}
EXPECTED_PROJECT = "DEMO - Marriott Residence Inn Client Work Group"
EXPECTED_INVOICE_REMARKS = "DEMO-BARO-INVOICE-001%"


def ok(label: str, detail: str = "") -> None:
    suffix = f": {detail}" if detail else ""
    print(f"OK   {label}{suffix}")


def fail(label: str, detail: str = "") -> None:
    suffix = f": {detail}" if detail else ""
    print(f"FAIL {label}{suffix}")


def exists_one(client: ERPNextClient, doctype: str, filters: list[Any], fields: list[str] | None = None) -> dict[str, Any] | None:
    return client.find_one(doctype, filters=filters, fields=fields or ["name"])


def main() -> int:
    client = ERPNextClient(ERPNextConfig.from_env())
    failures = 0

    print("Checking Baro CRM demo environment...")

    if exists_one(client, "Workspace", [["Workspace", "label", "=", EXPECTED_WORKSPACE]]):
        ok("Workspace", EXPECTED_WORKSPACE)
    else:
        fail("Workspace", EXPECTED_WORKSPACE)
        failures += 1

    if exists_one(client, "Kanban Board", [["Kanban Board", "kanban_board_name", "=", EXPECTED_KANBAN]]):
        ok("Kanban Board", EXPECTED_KANBAN)
    else:
        fail("Kanban Board", EXPECTED_KANBAN)
        failures += 1

    for label in EXPECTED_NUMBER_CARDS:
        if exists_one(client, "Number Card", [["Number Card", "label", "=", label]]):
            ok("Number Card", label)
        else:
            fail("Number Card", label)
            failures += 1

    for item_code in EXPECTED_ITEMS:
        if exists_one(client, "Item", [["Item", "item_code", "=", item_code]]):
            ok("Item", item_code)
        else:
            fail("Item", item_code)
            failures += 1

    for employee_name in EXPECTED_EMPLOYEES:
        if exists_one(client, "Employee", [["Employee", "employee_name", "=", employee_name]]):
            ok("Employee", employee_name)
        else:
            fail("Employee", employee_name)
            failures += 1

    for call_id, expected_status in EXPECTED_REPAIR_STATUSES.items():
        record = exists_one(
            client,
            "Repair Job",
            [["Repair Job", "zadarma_call_id", "=", call_id]],
            ["name", "status", "zadarma_call_id"],
        )
        if not record:
            fail("Repair Job", call_id)
            failures += 1
            continue
        if record.get("status") == expected_status:
            ok("Repair Job", f"{record['name']} / {expected_status}")
        else:
            fail("Repair Job Status", f"{record['name']} expected {expected_status}, got {record.get('status')}")
            failures += 1

    project = exists_one(
        client,
        "Project",
        [["Project", "project_name", "=", EXPECTED_PROJECT]],
        ["name", "project_name"],
    )
    if project:
        ok("Project", str(project["name"]))
    else:
        fail("Project", EXPECTED_PROJECT)
        failures += 1

    todos = client.list_docs(
        "ToDo",
        fields=["name", "description"],
        filters=[["ToDo", "description", "like", "DEMO-TODO-%"]],
        limit=20,
    )
    if len(todos) >= 5:
        ok("ToDo Count", str(len(todos)))
    else:
        fail("ToDo Count", f"expected >= 5, got {len(todos)}")
        failures += 1

    invoice = exists_one(
        client,
        "Sales Invoice",
        [["Sales Invoice", "remarks", "like", EXPECTED_INVOICE_REMARKS]],
        ["name", "status", "grand_total"],
    )
    if invoice:
        ok("Sales Invoice", f"{invoice['name']} / {invoice.get('status')} / ${invoice.get('grand_total')}")
    else:
        fail("Sales Invoice", EXPECTED_INVOICE_REMARKS)
        failures += 1

    if failures:
        print(f"Demo verification finished with failures: {failures}")
        return 1
    print("Demo verification finished successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

