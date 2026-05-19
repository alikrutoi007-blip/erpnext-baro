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


FORM_LAYOUT = [
    (
        "job_status_section",
        "1. Intake - Client, Status, Source",
        [
            "naming_series",
            "status",
            "customer",
            "caller_phone",
            "contact",
            "service_address",
            "area",
            "marketing_source",
            "business_phone_did",
        ],
        False,
    ),
    (
        "call_analysis_section",
        "2. Call Intelligence - What happened on the call",
        [
            "call_datetime",
            "call_duration_seconds",
            "purpose_of_call",
            "service_summary",
            "call_quality",
            "ai_call_summary",
            "client_information_from_call",
            "call_transcript",
        ],
        True,
    ),
    (
        "equipment_section",
        "3. Equipment and Problem",
        ["equipment_type", "equipment_brand", "equipment_model", "symptom", "urgency"],
        False,
    ),
    (
        "diagnostics_section",
        "4. Money - Diagnostic, Estimate, Approval",
        ["diagnostic_price", "prepayment_status", "estimate_amount", "client_approval_status"],
        False,
    ),
    (
        "client_group_section",
        "5. Team - Owner, Technician, Client Work Group",
        [
            "assigned_dispatcher",
            "estimate_manager",
            "production_manager",
            "technician",
            "mentor",
            "client_group_name",
            "client_group_project",
            "client_group_created_at",
            "client_group_members",
        ],
        True,
    ),
    (
        "estimate_parts_section",
        "6. Diagnosis and Parts",
        ["diagnosis_result", "parts_needed", "parts_status"],
        True,
    ),
    (
        "repair_warranty_section",
        "7. Repair, Payment, Warranty",
        ["repair_result", "warranty_start_date", "warranty_end_date", "next_follow_up_datetime"],
        False,
    ),
    (
        "internal_notes_section",
        "8. Internal Notes and Call Evidence",
        ["internal_comment", "zadarma_recording_url", "zadarma_call_id"],
        True,
    ),
]

REQUIRED_FIELDS = {
    "status",
    "customer",
    "caller_phone",
    "area",
    "purpose_of_call",
    "service_summary",
}

LIST_VIEW_FIELDS = {
    "status",
    "customer",
    "caller_phone",
    "area",
    "service_summary",
    "equipment_type",
    "technician",
    "prepayment_status",
}

STANDARD_FILTER_FIELDS = {
    "status",
    "customer",
    "area",
    "marketing_source",
    "equipment_type",
    "technician",
    "prepayment_status",
    "client_approval_status",
    "parts_status",
    "warranty_end_date",
    "call_datetime",
}

BOLD_FIELDS = {
    "status",
    "customer",
    "caller_phone",
    "purpose_of_call",
    "service_summary",
    "equipment_type",
    "technician",
    "diagnostic_price",
    "estimate_amount",
    "next_follow_up_datetime",
}

READ_ONLY_FIELDS = {
    "zadarma_recording_url",
    "zadarma_call_id",
    "call_datetime",
    "call_duration_seconds",
}

FIELD_DESCRIPTIONS = {
    "status": "Current workflow stage. Use the workflow buttons at the top of the form to move it forward.",
    "caller_phone": "Primary phone to search client history and call back.",
    "area": "Market/area from the DID or call source, used for routing and reporting.",
    "purpose_of_call": "Plain-English reason for the call. Keep it short and useful.",
    "service_summary": "One-line operational summary: service type, equipment, issue.",
    "equipment_type": "Example: espresso machine, hood, walk-in cooler, fryer.",
    "diagnostic_price": "Diagnostic/service-call amount discussed with the client.",
    "prepayment_status": "Shows whether dispatch is financially safe.",
    "estimate_amount": "Current estimate amount after diagnosis.",
    "client_approval_status": "Estimate approval stage.",
    "parts_status": "Supply handoff status.",
    "next_follow_up_datetime": "Used by customer care so warranty/follow-up is not forgotten.",
    "internal_comment": "Manager-facing notes and next action. Not customer-facing.",
}

KANBAN_DEFINITIONS = [
    {
        "name": "Baro Dispatch Board",
        "statuses": ["New", "Need Follow-up", "Diagnostics Offered", "Waiting Prepayment"],
        "color": "Blue",
        "fields": ["customer", "caller_phone", "area", "marketing_source", "purpose_of_call", "prepayment_status"],
    },
    {
        "name": "Baro Production Board",
        "statuses": [
            "Diagnostics Paid",
            "Technician Assigned",
            "Diagnostics In Progress",
            "Diagnosis Completed",
            "Parts Needed",
            "Repair In Progress",
            "Repair Completed",
        ],
        "color": "Orange",
        "fields": ["customer", "area", "equipment_type", "technician", "parts_status", "next_follow_up_datetime"],
    },
    {
        "name": "Baro Manager Board",
        "statuses": ["Estimate Sent", "Waiting Client Approval", "Invoice Sent", "Paid", "Warranty Active"],
        "color": "Green",
        "fields": ["customer", "area", "estimate_amount", "client_approval_status", "warranty_end_date"],
    },
]

NUMBER_CARD_DEFINITIONS = [
    ("Baro Dispatch Queue", [["Repair Job", "status", "in", ["New", "Need Follow-up", "Diagnostics Offered", "Waiting Prepayment"]]]),
    ("Baro Production Queue", [["Repair Job", "status", "in", ["Diagnostics Paid", "Technician Assigned", "Diagnostics In Progress", "Parts Needed", "Repair In Progress"]]]),
    ("Baro Estimate Approval Queue", [["Repair Job", "status", "in", ["Estimate Sent", "Waiting Client Approval"]]]),
    ("Baro Warranty Follow-up Queue", [["Repair Job", "status", "=", "Warranty Active"]]),
    ("Baro Paid Jobs", [["Repair Job", "status", "=", "Paid"]]),
]


FORM_CLIENT_SCRIPT = r"""
frappe.ui.form.on('Repair Job', {
  refresh(frm) {
    if (frm.is_new()) {
      return;
    }

    const group = __('Baro Actions');

    if (frm.doc.customer) {
      frm.add_custom_button(__('Open Customer'), () => {
        frappe.set_route('Form', 'Customer', frm.doc.customer);
      }, group);
    }

    if (frm.doc.contact) {
      frm.add_custom_button(__('Open Contact'), () => {
        frappe.set_route('Form', 'Contact', frm.doc.contact);
      }, group);
    }

    if (frm.doc.service_address) {
      frm.add_custom_button(__('Open Address'), () => {
        frappe.set_route('Form', 'Address', frm.doc.service_address);
      }, group);
    }

    if (frm.doc.client_group_project) {
      frm.add_custom_button(__('Open Client Group'), () => {
        frappe.set_route('Form', 'Project', frm.doc.client_group_project);
      }, group);
    }

    if (frm.doc.zadarma_recording_url) {
      frm.add_custom_button(__('Open Recording'), () => {
        window.open(frm.doc.zadarma_recording_url, '_blank');
      }, group);
    }

    frm.add_custom_button(__('Create Follow-up ToDo'), () => {
      frappe.call({
        method: 'frappe.client.insert',
        args: {
          doc: {
            doctype: 'ToDo',
            status: 'Open',
            priority: 'Medium',
            allocated_to: frappe.session.user,
            date: frappe.datetime.add_days(frappe.datetime.get_today(), 1),
            reference_type: 'Repair Job',
            reference_name: frm.doc.name,
            description: `Follow up ${frm.doc.customer || frm.doc.name}: ${frm.doc.status || ''}`
          }
        },
        callback: (r) => {
          if (!r.exc) {
            frappe.show_alert({message: __('Follow-up ToDo created'), indicator: 'green'});
          }
        }
      });
    }, group);
  }
});
"""

LIST_CLIENT_SCRIPT = r"""
frappe.listview_settings['Repair Job'] = {
  add_fields: [
    'status',
    'customer',
    'area',
    'technician',
    'prepayment_status',
    'client_approval_status',
    'parts_status',
    'warranty_end_date'
  ],
  get_indicator(doc) {
    const color_map = {
      'New': 'blue',
      'Need Follow-up': 'orange',
      'Diagnostics Offered': 'blue',
      'Waiting Prepayment': 'yellow',
      'Diagnostics Paid': 'green',
      'Technician Assigned': 'purple',
      'Diagnostics In Progress': 'purple',
      'Diagnosis Completed': 'green',
      'Estimate Sent': 'cyan',
      'Waiting Client Approval': 'orange',
      'Parts Needed': 'red',
      'Repair In Progress': 'purple',
      'Repair Completed': 'green',
      'Invoice Sent': 'blue',
      'Paid': 'green',
      'Warranty Active': 'cyan',
      'Closed': 'gray',
      'Lost': 'red',
      'Spam': 'red',
      'Unrelated': 'gray'
    };
    const color = color_map[doc.status] || 'gray';
    return [__(doc.status || 'Unknown'), color, `status,=,${doc.status}`];
  }
};
"""


def create_or_update_by_field(
    client: ERPNextClient,
    doctype: str,
    field: str,
    value: str,
    doc: dict[str, Any],
) -> str:
    existing = client.find_one(
        doctype,
        filters=[[doctype, field, "=", value]],
        fields=["name", field],
    )
    if existing:
        name = str(existing["name"])
        result = client.update_doc(doctype, name, doc)
        return str(result.get("name") or name)
    result = client.create_doc(doctype, doc)
    return str(result.get("name") or value)


def create_or_update_by_filters(
    client: ERPNextClient,
    doctype: str,
    filters: list[Any],
    doc: dict[str, Any],
    *,
    fields: list[str] | None = None,
) -> str:
    existing = client.find_one(doctype, filters=filters, fields=fields or ["name"])
    if existing:
        name = str(existing["name"])
        result = client.update_doc(doctype, name, doc)
        return str(result.get("name") or name)
    result = client.create_doc(doctype, doc)
    return str(result.get("name") or doc.get("name") or doctype)


def as_child_field(existing: dict[str, Any] | None, fieldname: str, fieldtype: str, idx: int, label: str | None = None) -> dict[str, Any]:
    field = dict(existing or {})
    field.update({"fieldname": fieldname, "fieldtype": fieldtype, "idx": idx})
    if label is not None:
        field["label"] = label
    return field


def build_enhanced_fields(doc: dict[str, Any]) -> list[dict[str, Any]]:
    current = {field["fieldname"]: field for field in doc.get("fields", []) if field.get("fieldname")}
    desired_fields: list[dict[str, Any]] = []
    idx = 1

    for section_fieldname, section_label, fieldnames, collapsible in FORM_LAYOUT:
        section = as_child_field(current.get(section_fieldname), section_fieldname, "Section Break", idx, section_label)
        section["collapsible"] = 1 if collapsible else 0
        desired_fields.append(section)
        idx += 1

        midpoint = max(2, (len(fieldnames) + 1) // 2)
        for position, fieldname in enumerate(fieldnames):
            if position == midpoint:
                column_fieldname = f"{section_fieldname}_column_break"
                desired_fields.append(as_child_field(current.get(column_fieldname), column_fieldname, "Column Break", idx))
                idx += 1

            if fieldname not in current:
                raise RuntimeError(f"Repair Job field is missing in ERPNext: {fieldname}")
            field = dict(current[fieldname])
            field["idx"] = idx
            field["reqd"] = 1 if fieldname in REQUIRED_FIELDS else 0
            field["in_list_view"] = 1 if fieldname in LIST_VIEW_FIELDS else 0
            field["in_standard_filter"] = 1 if fieldname in STANDARD_FILTER_FIELDS else 0
            field["bold"] = 1 if fieldname in BOLD_FIELDS else 0
            field["read_only"] = 1 if fieldname in READ_ONLY_FIELDS else 0
            field["hidden"] = 1 if fieldname == "naming_series" else 0
            if fieldname in FIELD_DESCRIPTIONS:
                field["description"] = FIELD_DESCRIPTIONS[fieldname]
            if fieldname in {"call_transcript", "internal_comment", "diagnosis_result", "repair_result"}:
                field["columns"] = 12
            desired_fields.append(field)
            idx += 1

    seen = set()
    duplicates = []
    for field in desired_fields:
        fieldname = field.get("fieldname")
        if fieldname in seen:
            duplicates.append(fieldname)
        seen.add(fieldname)
    if duplicates:
        raise RuntimeError(f"Duplicate fieldnames in enhanced layout: {duplicates}")
    return desired_fields


def enhance_repair_job_doctype(client: ERPNextClient) -> list[str]:
    doc = client.get_doc("DocType", "Repair Job")
    enhanced_fields = build_enhanced_fields(doc)
    changes = [
        "Reordered Repair Job form into role-friendly sections",
        "Marked required intake fields: status, customer, caller phone, area, purpose, service summary",
        "Improved list view and standard filters",
        "Hid naming series from daily users",
        "Collapsed long AI/team/evidence sections",
    ]
    doc["fields"] = enhanced_fields
    doc["field_order"] = [field["fieldname"] for field in enhanced_fields]
    doc["title_field"] = "customer"
    doc["search_fields"] = "customer,caller_phone,area,marketing_source,equipment_type,service_summary,zadarma_call_id"
    doc["sort_field"] = "modified"
    doc["sort_order"] = "DESC"
    doc["track_changes"] = 1
    if client.config.dry_run:
        return changes
    client.update_doc("DocType", "Repair Job", doc)
    try:
        client._request("POST", "/api/method/frappe.clear_cache", payload={"doctype": "Repair Job"})
    except ERPNextError as exc:
        print(f"WARN could not clear cache automatically: {exc}")
    return changes


def ensure_number_card(client: ERPNextClient, label: str, filters: list[Any]) -> str:
    doc = {
        "doctype": "Number Card",
        "label": label,
        "type": "Document Type",
        "document_type": "Repair Job",
        "function": "Count",
        "is_public": 1,
        "module": "Custom",
        "show_full_number": 1,
        "filters_json": json.dumps(filters),
    }
    return create_or_update_by_field(client, "Number Card", "label", label, doc)


def ensure_kanban(client: ERPNextClient, definition: dict[str, Any]) -> str:
    statuses = definition["statuses"]
    doc = {
        "doctype": "Kanban Board",
        "kanban_board_name": definition["name"],
        "reference_doctype": "Repair Job",
        "field_name": "status",
        "private": 0,
        "show_labels": 1,
        "columns": [
            {"column_name": status, "status": "Active", "indicator": definition["color"]}
            for status in statuses
        ],
        "filters": json.dumps([["Repair Job", "status", "in", statuses]]),
        "fields": json.dumps(definition["fields"]),
    }
    return create_or_update_by_field(client, "Kanban Board", "kanban_board_name", definition["name"], doc)


def workspace_content(title: str, subtitle: str, number_cards: list[str]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [
        {
            "id": f"{title.lower().replace(' ', '-')}-header",
            "type": "header",
            "data": {
                "text": f"<span class=\"h4\"><b>{title}</b></span><br>{subtitle}",
                "col": 12,
            },
        }
    ]
    for index, card in enumerate(number_cards, start=1):
        content.append(
            {
                "id": f"{title.lower().replace(' ', '-')}-card-{index}",
                "type": "number_card",
                "data": {"number_card_name": card, "col": 4},
            }
        )
    return content


def ensure_workspace(
    client: ERPNextClient,
    *,
    label: str,
    subtitle: str,
    kanban: str,
    cards: list[str],
    color: str,
    quick_filters: list[tuple[str, list[Any]]],
    extra_shortcuts: list[dict[str, Any]] | None = None,
) -> str:
    shortcuts = [
        {"type": "DocType", "link_to": "Repair Job", "doc_view": "Kanban", "kanban_board": kanban, "label": "Main Board", "icon": "kanban"},
        {"type": "DocType", "link_to": "Repair Job", "doc_view": "List", "label": "Repair Jobs", "icon": "list"},
        {"type": "DocType", "link_to": "ToDo", "doc_view": "List", "label": "Follow-up ToDos", "icon": "check"},
    ]
    if extra_shortcuts:
        shortcuts.extend(extra_shortcuts)

    quick_lists = [
        {
            "document_type": "Repair Job",
            "label": quick_label,
            "quick_list_filter": json.dumps(filters),
        }
        for quick_label, filters in quick_filters
    ]
    links = [
        {"type": "Card Break", "label": "Daily Work"},
        {"type": "Link", "label": "Repair Job", "link_type": "DocType", "link_to": "Repair Job", "onboard": 1},
        {"type": "Link", "label": "ToDo", "link_type": "DocType", "link_to": "ToDo", "onboard": 1},
        {"type": "Card Break", "label": "Records"},
        {"type": "Link", "label": "Customer", "link_type": "DocType", "link_to": "Customer", "onboard": 1},
        {"type": "Link", "label": "Contact", "link_type": "DocType", "link_to": "Contact", "onboard": 1},
        {"type": "Link", "label": "Address", "link_type": "DocType", "link_to": "Address", "onboard": 1},
    ]
    doc = {
        "doctype": "Workspace",
        "label": label,
        "title": label,
        "module": "Custom",
        "type": "Workspace",
        "public": 1,
        "is_hidden": 0,
        "icon": "crm",
        "indicator_color": color,
        "content": json.dumps(workspace_content(label, subtitle, cards)),
        "shortcuts": shortcuts,
        "links": links,
        "quick_lists": quick_lists,
        "number_cards": [{"number_card_name": card, "label": card} for card in cards],
    }
    return create_or_update_by_field(client, "Workspace", "label", label, doc)


def ensure_role_views(client: ERPNextClient) -> dict[str, Any]:
    cards = [ensure_number_card(client, label, filters) for label, filters in NUMBER_CARD_DEFINITIONS]
    boards = {definition["name"]: ensure_kanban(client, definition) for definition in KANBAN_DEFINITIONS}

    workspaces = [
        ensure_workspace(
            client,
            label="Baro Dispatch Desk",
            subtitle="For dispatchers: capture the client, sell diagnostics, prevent missed follow-up.",
            kanban=boards["Baro Dispatch Board"],
            cards=["Baro Dispatch Queue", "Baro Needs Follow-up", "Baro Open Repair Jobs"],
            color="blue",
            quick_filters=[
                ("New and Unworked", [["Repair Job", "status", "in", ["New", "Need Follow-up"]]]),
                ("Waiting Prepayment", [["Repair Job", "status", "=", "Waiting Prepayment"]]),
                ("Diagnostics Offered", [["Repair Job", "status", "=", "Diagnostics Offered"]]),
            ],
            extra_shortcuts=[
                {"type": "DocType", "link_to": "Customer", "doc_view": "List", "label": "Customer Cards", "icon": "customer"},
            ],
        ),
        ensure_workspace(
            client,
            label="Baro Production Desk",
            subtitle="For production: assign technicians, track diagnosis, parts, repair progress.",
            kanban=boards["Baro Production Board"],
            cards=["Baro Production Queue", "Baro Active Repairs", "Baro Open Repair Jobs"],
            color="orange",
            quick_filters=[
                ("Technician Assigned", [["Repair Job", "status", "=", "Technician Assigned"]]),
                ("Parts Needed", [["Repair Job", "status", "=", "Parts Needed"]]),
                ("Repair In Progress", [["Repair Job", "status", "=", "Repair In Progress"]]),
            ],
            extra_shortcuts=[
                {"type": "DocType", "link_to": "Employee", "doc_view": "List", "label": "Technicians", "icon": "users"},
                {"type": "DocType", "link_to": "Item", "doc_view": "List", "label": "Service Items", "icon": "item"},
            ],
        ),
        ensure_workspace(
            client,
            label="Baro Manager Desk",
            subtitle="For managers: estimate approvals, invoices, paid jobs, warranty follow-up.",
            kanban=boards["Baro Manager Board"],
            cards=["Baro Estimate Approval Queue", "Baro Warranty Follow-up Queue", "Baro Paid Jobs"],
            color="green",
            quick_filters=[
                ("Estimate Follow-up", [["Repair Job", "status", "in", ["Estimate Sent", "Waiting Client Approval"]]]),
                ("Paid Jobs", [["Repair Job", "status", "=", "Paid"]]),
                ("Warranty Active", [["Repair Job", "status", "=", "Warranty Active"]]),
            ],
            extra_shortcuts=[
                {"type": "DocType", "link_to": "Sales Invoice", "doc_view": "List", "label": "Invoices", "icon": "money"},
                {"type": "DocType", "link_to": "Project", "doc_view": "List", "label": "Client Work Groups", "icon": "project"},
            ],
        ),
    ]

    return {"number_cards": cards, "boards": boards, "workspaces": workspaces}


def ensure_client_scripts(client: ERPNextClient) -> list[str]:
    scripts = []
    form_doc = {
        "doctype": "Client Script",
        "name": "Baro Repair Job Form UX",
        "dt": "Repair Job",
        "view": "Form",
        "enabled": 1,
        "module": "Custom",
        "script": FORM_CLIENT_SCRIPT.strip(),
    }
    scripts.append(
        create_or_update_by_filters(
            client,
            "Client Script",
            [["Client Script", "name", "=", "Baro Repair Job Form UX"]],
            form_doc,
            fields=["name", "dt", "view"],
        )
    )

    list_doc = {
        "doctype": "Client Script",
        "name": "Baro Repair Job List UX",
        "dt": "Repair Job",
        "view": "List",
        "enabled": 1,
        "module": "Custom",
        "script": LIST_CLIENT_SCRIPT.strip(),
    }
    scripts.append(
        create_or_update_by_filters(
            client,
            "Client Script",
            [["Client Script", "name", "=", "Baro Repair Job List UX"]],
            list_doc,
            fields=["name", "dt", "view"],
        )
    )
    return scripts


def main() -> int:
    parser = argparse.ArgumentParser(description="Enhance Repair Job form UX, quick actions, and role workspaces.")
    parser.add_argument("--execute", action="store_true", help="Actually update ERPNext. Default is dry-run.")
    args = parser.parse_args()

    config = ERPNextConfig.from_env()
    if args.execute:
        config = replace(config, dry_run=False)
    client = ERPNextClient(config)

    print(f"ERPNext site: {config.base_url}")
    print(f"Mode: {'EXECUTE' if args.execute else 'DRY RUN'}")

    doctype_changes = enhance_repair_job_doctype(client)
    role_views = ensure_role_views(client)
    scripts = ensure_client_scripts(client)

    print(json.dumps(
        {
            "doctype_changes": doctype_changes,
            "role_views": role_views,
            "client_scripts": scripts,
        },
        indent=2,
        ensure_ascii=False,
    ))

    if not args.execute:
        print("Dry run complete. Re-run with --execute to apply the Repair Job UX enhancements.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
