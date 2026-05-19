from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from erpnext_client import ERPNextClient, ERPNextConfig


REQUIRED_FIELDS = {
    "status",
    "customer",
    "caller_phone",
    "area",
    "purpose_of_call",
    "service_summary",
}

EXPECTED_SECTIONS = {
    "job_status_section": "1. Intake - Client, Status, Source",
    "call_analysis_section": "2. Call Intelligence - What happened on the call",
    "equipment_section": "3. Equipment and Problem",
    "diagnostics_section": "4. Money - Diagnostic, Estimate, Approval",
    "client_group_section": "5. Team - Owner, Technician, Client Work Group",
    "estimate_parts_section": "6. Diagnosis and Parts",
    "repair_warranty_section": "7. Repair, Payment, Warranty",
    "internal_notes_section": "8. Internal Notes and Call Evidence",
}

EXPECTED_BOARDS = [
    "Baro Dispatch Board",
    "Baro Production Board",
    "Baro Manager Board",
]

EXPECTED_WORKSPACES = [
    "Baro Dispatch Desk",
    "Baro Production Desk",
    "Baro Manager Desk",
]

EXPECTED_NUMBER_CARDS = [
    "Baro Dispatch Queue",
    "Baro Production Queue",
    "Baro Estimate Approval Queue",
    "Baro Warranty Follow-up Queue",
    "Baro Paid Jobs",
]

EXPECTED_CLIENT_SCRIPTS = [
    ("Baro Repair Job Form UX", "Form"),
    ("Baro Repair Job List UX", "List"),
]


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

    print("Checking Repair Job UX enhancements...")

    doc = client.get_doc("DocType", "Repair Job")
    fields = {field.get("fieldname"): field for field in doc.get("fields", []) if field.get("fieldname")}

    for fieldname, expected_label in EXPECTED_SECTIONS.items():
        field = fields.get(fieldname)
        if field and field.get("label") == expected_label:
            ok("Form Section", expected_label)
        else:
            fail("Form Section", f"{fieldname} expected {expected_label!r}")
            failures += 1

    for fieldname in REQUIRED_FIELDS:
        field = fields.get(fieldname)
        if field and field.get("reqd") == 1:
            ok("Required Field", fieldname)
        else:
            fail("Required Field", fieldname)
            failures += 1

    naming_series = fields.get("naming_series")
    if naming_series and naming_series.get("hidden") == 1:
        ok("Hidden Field", "naming_series")
    else:
        fail("Hidden Field", "naming_series should be hidden")
        failures += 1

    if fields.get("call_analysis_section", {}).get("collapsible") == 1:
        ok("Collapsible Section", "Call Intelligence")
    else:
        fail("Collapsible Section", "Call Intelligence")
        failures += 1

    for board in EXPECTED_BOARDS:
        if exists_one(client, "Kanban Board", [["Kanban Board", "kanban_board_name", "=", board]]):
            ok("Kanban Board", board)
        else:
            fail("Kanban Board", board)
            failures += 1

    for workspace in EXPECTED_WORKSPACES:
        if exists_one(client, "Workspace", [["Workspace", "label", "=", workspace]]):
            ok("Workspace", workspace)
        else:
            fail("Workspace", workspace)
            failures += 1

    for card in EXPECTED_NUMBER_CARDS:
        if exists_one(client, "Number Card", [["Number Card", "label", "=", card]]):
            ok("Number Card", card)
        else:
            fail("Number Card", card)
            failures += 1

    for script_name, view in EXPECTED_CLIENT_SCRIPTS:
        script = exists_one(
            client,
            "Client Script",
            [["Client Script", "name", "=", script_name]],
            ["name", "dt", "view", "enabled"],
        )
        if script and script.get("dt") == "Repair Job" and script.get("view") == view and script.get("enabled") == 1:
            ok("Client Script", f"{script_name} / {view}")
        else:
            fail("Client Script", script_name)
            failures += 1

    if failures:
        print(f"Repair Job UX verification finished with failures: {failures}")
        return 1
    print("Repair Job UX verification finished successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

