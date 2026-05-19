from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from erpnext_client import ERPNextClient, ERPNextConfig, ERPNextError


SECTION_LAYOUT = [
    ("job_status_section", "Job Status", ["naming_series", "status"]),
    ("customer_details_section", "Customer Details", ["customer", "contact", "service_address", "caller_phone", "business_phone_did"]),
    ("call_source_section", "Call Source", ["area", "marketing_source", "zadarma_recording_url", "zadarma_call_id", "call_datetime", "call_duration_seconds"]),
    ("call_analysis_section", "Call Analysis", ["call_quality", "purpose_of_call", "client_information_from_call", "service_summary", "ai_call_summary", "call_transcript"]),
    ("equipment_section", "Equipment And Issue", ["equipment_type", "equipment_brand", "equipment_model", "symptom", "urgency"]),
    ("diagnostics_section", "Diagnostics And Assignment", ["diagnostic_price", "prepayment_status", "assigned_dispatcher", "estimate_manager", "production_manager", "technician", "mentor", "diagnosis_result"]),
    ("client_group_section", "Client Group And Tasks", ["client_group_name", "client_group_project", "client_group_created_at", "client_group_members"]),
    ("estimate_parts_section", "Estimate And Parts", ["estimate_amount", "client_approval_status", "parts_needed", "parts_status"]),
    ("repair_warranty_section", "Repair And Warranty", ["repair_result", "warranty_start_date", "warranty_end_date", "next_follow_up_datetime"]),
    ("internal_notes_section", "Internal Notes", ["internal_comment"]),
]

LIST_VIEW_FIELDS = {
    "status",
    "customer",
    "caller_phone",
    "area",
    "marketing_source",
    "equipment_type",
    "technician",
    "call_datetime",
}

STANDARD_FILTER_FIELDS = {
    "status",
    "customer",
    "area",
    "marketing_source",
    "equipment_type",
    "technician",
    "call_datetime",
    "prepayment_status",
    "parts_status",
}

SEARCH_FIELDS = [
    "customer",
    "caller_phone",
    "zadarma_recording_url",
    "area",
    "marketing_source",
    "equipment_type",
]


PERMISSIONS = [
    {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1, "submit": 0, "cancel": 0, "amend": 0, "report": 1, "export": 1, "import": 1, "share": 1, "print": 1, "email": 1},
    {"role": "Sales Manager", "read": 1, "write": 1, "create": 1, "delete": 0, "report": 1, "export": 1, "share": 1, "print": 1, "email": 1},
    {"role": "Sales User", "read": 1, "write": 1, "create": 1, "delete": 0, "report": 1, "print": 1, "email": 1},
    {"role": "Support Team", "read": 1, "write": 1, "create": 1, "delete": 0, "report": 1, "print": 1, "email": 1},
    {"role": "Maintenance Manager", "read": 1, "write": 1, "create": 1, "delete": 0, "report": 1, "export": 1, "share": 1, "print": 1, "email": 1},
    {"role": "Maintenance User", "read": 1, "write": 1, "create": 0, "delete": 0, "report": 1, "print": 1},
    {"role": "Accounts User", "read": 1, "write": 0, "create": 0, "delete": 0, "report": 1, "print": 1},
]


def load_schema() -> dict[str, Any]:
    return json.loads((ROOT / "config" / "repair_job_schema.json").read_text(encoding="utf-8"))


def field_map(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    fields = {field["fieldname"]: dict(field) for field in schema["fields"]}
    fields["naming_series"] = {
        "fieldname": "naming_series",
        "label": "Series",
        "fieldtype": "Select",
        "options": schema["naming_series"],
        "required": True,
        "default": schema["naming_series"],
    }
    return fields


def make_docfield(raw: dict[str, Any], idx: int) -> dict[str, Any]:
    fieldname = raw["fieldname"]
    docfield = {
        "fieldname": fieldname,
        "label": raw.get("label"),
        "fieldtype": raw["fieldtype"],
        "idx": idx,
    }
    if raw.get("options") is not None:
        docfield["options"] = raw["options"]
    if raw.get("required"):
        docfield["reqd"] = 1
    if raw.get("default") is not None:
        docfield["default"] = raw["default"]
    if raw.get("unique"):
        docfield["unique"] = 1
    if fieldname in LIST_VIEW_FIELDS:
        docfield["in_list_view"] = 1
    if fieldname in STANDARD_FILTER_FIELDS:
        docfield["in_standard_filter"] = 1
    if fieldname in SEARCH_FIELDS:
        docfield["search_index"] = 1
    if raw["fieldtype"] in {"Long Text", "Small Text"}:
        docfield["in_global_search"] = 1
    return {key: value for key, value in docfield.items() if value is not None}


def build_payload(schema: dict[str, Any]) -> dict[str, Any]:
    fields_by_name = field_map(schema)
    fields: list[dict[str, Any]] = []
    field_order: list[str] = []
    idx = 1

    for section_fieldname, section_label, names in SECTION_LAYOUT:
        fields.append({
            "fieldname": section_fieldname,
            "label": section_label,
            "fieldtype": "Section Break",
            "idx": idx,
        })
        field_order.append(section_fieldname)
        idx += 1

        midpoint = max(2, (len(names) + 1) // 2)
        for pos, name in enumerate(names):
            if pos == midpoint:
                column_fieldname = f"{section_fieldname}_column_break"
                fields.append({"fieldname": column_fieldname, "fieldtype": "Column Break", "idx": idx})
                field_order.append(column_fieldname)
                idx += 1
            fields.append(make_docfield(fields_by_name[name], idx))
            field_order.append(name)
            idx += 1

    return {
        "doctype": "DocType",
        "name": schema["doctype"],
        "module": "Custom",
        "custom": 1,
        "document_type": "Document",
        "is_submittable": 0,
        "allow_import": 1,
        "allow_rename": 1,
        "track_changes": 1,
        "quick_entry": 0,
        "autoname": "naming_series:",
        "naming_rule": "By \"Naming Series\" field",
        "title_field": "customer",
        "search_fields": ",".join(SEARCH_FIELDS),
        "sort_field": "modified",
        "sort_order": "DESC",
        "description": schema["description"],
        "field_order": field_order,
        "fields": fields,
        "permissions": PERMISSIONS,
    }


def doctype_exists(client: ERPNextClient, name: str) -> bool:
    return bool(client.find_by_field("DocType", "name", name, limit=1))


def main() -> int:
    parser = argparse.ArgumentParser(description="Create Baro Repair Job custom DocType in ERPNext.")
    parser.add_argument("--execute", action="store_true", help="Actually create the DocType. Default prints dry-run payload.")
    parser.add_argument("--print-payload", action="store_true", help="Print JSON payload for review.")
    args = parser.parse_args()

    schema = load_schema()
    payload = build_payload(schema)
    config = ERPNextConfig.from_env()
    if args.execute:
        config = replace(config, dry_run=False)
    client = ERPNextClient(config)

    print(f"ERPNext site: {config.base_url}")
    print(f"Target DocType: {schema['doctype']}")
    print(f"Mode: {'EXECUTE' if args.execute else 'DRY RUN'}")

    if doctype_exists(client, schema["doctype"]):
        print("Repair Job already exists. No create action taken.")
        return 0

    if args.print_payload or not args.execute:
        print(json.dumps(payload, indent=2, ensure_ascii=False))

    if not args.execute:
        print("Dry run complete. Re-run with --execute to create in ERPNext.")
        return 0

    created = client.create_doc("DocType", payload)
    print(f"Created DocType: {created.get('name')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
