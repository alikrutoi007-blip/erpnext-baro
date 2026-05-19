from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from erpnext_client import ERPNextClient, ERPNextConfig, ERPNextError


DEMO_JOBS = [
    {
        "customer": "DEMO - Sunrise Diner",
        "contact": "Maria Lopez",
        "phone": "+12125550101",
        "address": "120 W 31st St",
        "city": "New York",
        "state": "NY",
        "area": "USA, New York + SMS",
        "source": "BaroSite NY",
        "status": "Diagnostics Offered",
        "equipment": "Commercial fryer",
        "summary": "Diagnostics - fryer pilot shuts off",
        "purpose": "Customer needs same-day diagnostics for a fryer before dinner service.",
        "comment": "Demo story: incoming call -> dispatcher verifies client -> diagnostic sale.",
        "diagnostic_price": 199,
        "estimate_amount": 0,
        "prepayment_status": "Requested",
        "client_approval_status": "Not Sent",
        "parts_needed": 0,
        "parts_status": "Not Needed",
        "diagnosis_result": "",
        "repair_result": "",
        "technician": "",
        "next_action": "Collect diagnostic prepayment and schedule technician.",
    },
    {
        "customer": "DEMO - Gulf Coast Grill",
        "contact": "Daniel Price",
        "phone": "+18135550102",
        "address": "420 S Howard Ave",
        "city": "Tampa",
        "state": "FL",
        "area": "USA, Tampa + SMS",
        "source": "Tampa-Miami",
        "status": "Waiting Prepayment",
        "equipment": "Walk-in cooler",
        "summary": "Diagnostics - walk-in cooler not holding temperature",
        "purpose": "Customer accepted diagnostics; waiting for prepayment before dispatch.",
        "comment": "Demo story: prevents unpaid dispatches and makes handoff visible.",
        "diagnostic_price": 259,
        "estimate_amount": 0,
        "prepayment_status": "Requested",
        "client_approval_status": "Not Sent",
        "parts_needed": 0,
        "parts_status": "Not Needed",
        "diagnosis_result": "",
        "repair_result": "",
        "technician": "",
        "next_action": "Follow up for prepayment before sending technician.",
    },
    {
        "customer": "DEMO - Harbor Sushi",
        "contact": "Ken Watanabe",
        "phone": "+17865550103",
        "address": "88 Biscayne Blvd",
        "city": "Miami",
        "state": "FL",
        "area": "USA, Miami + SMS",
        "source": "Miami site",
        "status": "Technician Assigned",
        "equipment": "Ice machine",
        "summary": "Repair - ice machine leaking",
        "purpose": "Technician assigned; manager needs ETA and job visibility.",
        "comment": "Demo story: dispatcher and production manager see ownership.",
        "diagnostic_price": 199,
        "estimate_amount": 0,
        "prepayment_status": "Paid",
        "client_approval_status": "Not Sent",
        "parts_needed": 0,
        "parts_status": "Not Needed",
        "diagnosis_result": "",
        "repair_result": "",
        "technician": "DEMO - Omar Technician",
        "next_action": "Technician confirms ETA and starts diagnostics.",
    },
    {
        "customer": "DEMO - Brooklyn Coffee Lab",
        "contact": "Ava Chen",
        "phone": "+13475550104",
        "address": "305 Atlantic Ave",
        "city": "New York",
        "state": "NY",
        "area": "USA, New York + SMS",
        "source": "NYGoogleReklama2",
        "status": "Estimate Sent",
        "equipment": "Espresso machine",
        "summary": "Estimate - espresso machine pump replacement",
        "purpose": "Estimate sent after diagnosis; waiting for client approval.",
        "comment": "Demo story: estimate manager owns approval follow-up.",
        "diagnostic_price": 199,
        "estimate_amount": 645,
        "prepayment_status": "Paid",
        "client_approval_status": "Sent",
        "parts_needed": 1,
        "parts_status": "Need Identify",
        "diagnosis_result": "Pump pressure is unstable. Recommend pump replacement and calibration.",
        "repair_result": "",
        "technician": "DEMO - Omar Technician",
        "next_action": "Estimate manager follows up for approval before ordering parts.",
    },
    {
        "customer": "DEMO - Orlando Pizza Works",
        "contact": "Samir Haddad",
        "phone": "+16895550105",
        "address": "730 Orange Ave",
        "city": "Orlando",
        "state": "FL",
        "area": "USA, Orlando + SMS",
        "source": "Orlando site",
        "status": "Parts Needed",
        "equipment": "Conveyor oven",
        "summary": "Parts - conveyor oven thermostat",
        "purpose": "Repair approved; supply needs to source thermostat.",
        "comment": "Demo story: supply handoff is visible instead of hidden in chat.",
        "diagnostic_price": 159,
        "estimate_amount": 780,
        "prepayment_status": "Paid",
        "client_approval_status": "Approved",
        "parts_needed": 1,
        "parts_status": "Ordered",
        "diagnosis_result": "Thermostat fails under load. Oven overheats after 20 minutes.",
        "repair_result": "",
        "technician": "DEMO - Diego Technician",
        "next_action": "Supply confirms thermostat ETA and production schedules return visit.",
    },
    {
        "customer": "DEMO - Houston BBQ House",
        "contact": "Chris Morgan",
        "phone": "+17135550106",
        "address": "2100 Main St",
        "city": "Houston",
        "state": "TX",
        "area": "USA, Houston + SMS",
        "source": "HoustonGoogleAds2",
        "status": "Repair In Progress",
        "equipment": "Restaurant hood",
        "summary": "Repair - hood motor replacement",
        "purpose": "Technician is on-site and repair is active.",
        "comment": "Demo story: production sees live repair status and next action.",
        "diagnostic_price": 199,
        "estimate_amount": 1180,
        "prepayment_status": "Paid",
        "client_approval_status": "Approved",
        "parts_needed": 1,
        "parts_status": "Received",
        "diagnosis_result": "Hood motor burned out; replacement approved by client.",
        "repair_result": "Technician replacing motor and testing airflow.",
        "technician": "DEMO - Diego Technician",
        "next_action": "Technician uploads completion note and photos after testing.",
    },
    {
        "customer": "DEMO - Sarasota Hotel Kitchen",
        "contact": "Laura Wells",
        "phone": "+17275550107",
        "address": "100 Bayfront Dr",
        "city": "Sarasota",
        "state": "FL",
        "area": "USA, St. Petersburg + SMS",
        "source": "Sarasota website",
        "status": "Paid",
        "equipment": "Commercial dishwasher",
        "summary": "Completed - dishwasher drain pump",
        "purpose": "Repair completed and paid; warranty should be tracked.",
        "comment": "Demo story: invoice/payment/warranty closure in one customer history.",
        "diagnostic_price": 159,
        "estimate_amount": 520,
        "prepayment_status": "Paid",
        "client_approval_status": "Approved",
        "parts_needed": 1,
        "parts_status": "Installed",
        "diagnosis_result": "Drain pump failed; water remained after cycle.",
        "repair_result": "Drain pump replaced; dishwasher tested through full cycle.",
        "technician": "DEMO - Omar Technician",
        "next_action": "Accounting confirms invoice/payment and activates warranty.",
    },
    {
        "customer": "DEMO - Vegas Buffet",
        "contact": "Nina Patel",
        "phone": "+17025550108",
        "address": "333 Flamingo Rd",
        "city": "Las Vegas",
        "state": "NV",
        "area": "USA, Las Vegas + SMS",
        "source": "LasVegassms",
        "status": "Warranty Active",
        "equipment": "Reach-in freezer",
        "summary": "Warranty - freezer follow-up",
        "purpose": "Warranty follow-up should happen before warranty expires.",
        "comment": "Demo story: customer care does not forget post-repair follow-up.",
        "diagnostic_price": 199,
        "estimate_amount": 690,
        "prepayment_status": "Paid",
        "client_approval_status": "Approved",
        "parts_needed": 1,
        "parts_status": "Installed",
        "diagnosis_result": "Compressor relay failure diagnosed and approved.",
        "repair_result": "Relay replaced; freezer reached target temperature after testing.",
        "technician": "DEMO - Diego Technician",
        "next_action": "Customer care checks freezer performance before warranty ends.",
    },
]

DEMO_EMPLOYEES = [
    {
        "name": "DEMO - Omar Technician",
        "first_name": "DEMO Omar",
        "designation": "Engineer",
        "department": "Production - BSL",
        "cell_number": "+17275559001",
        "ctc": 62000,
    },
    {
        "name": "DEMO - Diego Technician",
        "first_name": "DEMO Diego",
        "designation": "Engineer",
        "department": "Production - BSL",
        "cell_number": "+17275559002",
        "ctc": 64000,
    },
    {
        "name": "DEMO - Lena Dispatcher",
        "first_name": "DEMO Lena",
        "designation": "Customer Service Representative",
        "department": "Dispatch - BSL",
        "cell_number": "+17275559003",
        "ctc": 52000,
    },
]

DEMO_ITEMS = [
    {
        "item_code": "DEMO-DIAGNOSTIC-SERVICE",
        "item_name": "DEMO - Diagnostic Service Call",
        "standard_rate": 199,
    },
    {
        "item_code": "DEMO-REPAIR-LABOR",
        "item_name": "DEMO - Repair Labor",
        "standard_rate": 359,
    },
    {
        "item_code": "DEMO-PARTS",
        "item_name": "DEMO - Replacement Parts",
        "standard_rate": 180,
    },
]

REPAIR_JOB_STATUSES = [
    ("New", "Blue"),
    ("Need Follow-up", "Orange"),
    ("Waiting Prepayment", "Yellow"),
    ("Diagnostics Paid", "Green"),
    ("Technician Assigned", "Purple"),
    ("Estimate Sent", "Cyan"),
    ("Parts Needed", "Red"),
    ("Repair In Progress", "Pink"),
    ("Paid", "Green"),
    ("Warranty Active", "Light Blue"),
]

WORKFLOW_PATHS = {
    "New": [],
    "Need Follow-up": ["Mark Need Follow-up"],
    "Diagnostics Offered": ["Offer Diagnostics"],
    "Waiting Prepayment": ["Offer Diagnostics", "Request Prepayment"],
    "Diagnostics Paid": ["Offer Diagnostics", "Mark Diagnostics Paid"],
    "Technician Assigned": ["Offer Diagnostics", "Mark Diagnostics Paid", "Assign Technician"],
    "Diagnostics In Progress": ["Offer Diagnostics", "Mark Diagnostics Paid", "Assign Technician", "Start Diagnostics"],
    "Diagnosis Completed": ["Offer Diagnostics", "Mark Diagnostics Paid", "Assign Technician", "Start Diagnostics", "Complete Diagnosis"],
    "Estimate Sent": ["Offer Diagnostics", "Mark Diagnostics Paid", "Assign Technician", "Start Diagnostics", "Complete Diagnosis", "Send Estimate"],
    "Waiting Client Approval": ["Offer Diagnostics", "Mark Diagnostics Paid", "Assign Technician", "Start Diagnostics", "Complete Diagnosis", "Send Estimate", "Wait Client Approval"],
    "Parts Needed": ["Offer Diagnostics", "Mark Diagnostics Paid", "Assign Technician", "Start Diagnostics", "Complete Diagnosis", "Send Estimate", "Wait Client Approval", "Mark Parts Needed"],
    "Repair In Progress": ["Offer Diagnostics", "Mark Diagnostics Paid", "Assign Technician", "Start Diagnostics", "Complete Diagnosis", "Send Estimate", "Wait Client Approval", "Start Repair"],
    "Repair Completed": ["Offer Diagnostics", "Mark Diagnostics Paid", "Assign Technician", "Start Diagnostics", "Complete Diagnosis", "Send Estimate", "Wait Client Approval", "Start Repair", "Complete Repair"],
    "Invoice Sent": ["Offer Diagnostics", "Mark Diagnostics Paid", "Assign Technician", "Start Diagnostics", "Complete Diagnosis", "Send Estimate", "Wait Client Approval", "Start Repair", "Complete Repair", "Send Invoice"],
    "Paid": ["Offer Diagnostics", "Mark Diagnostics Paid", "Assign Technician", "Start Diagnostics", "Complete Diagnosis", "Send Estimate", "Wait Client Approval", "Start Repair", "Complete Repair", "Send Invoice", "Mark Paid"],
    "Warranty Active": ["Offer Diagnostics", "Mark Diagnostics Paid", "Assign Technician", "Start Diagnostics", "Complete Diagnosis", "Send Estimate", "Wait Client Approval", "Start Repair", "Complete Repair", "Send Invoice", "Mark Paid", "Activate Warranty"],
}

WORKFLOW_NEXT_STATE = {
    ("New", "Mark Need Follow-up"): "Need Follow-up",
    ("New", "Offer Diagnostics"): "Diagnostics Offered",
    ("Need Follow-up", "Offer Diagnostics"): "Diagnostics Offered",
    ("Diagnostics Offered", "Request Prepayment"): "Waiting Prepayment",
    ("Diagnostics Offered", "Mark Diagnostics Paid"): "Diagnostics Paid",
    ("Waiting Prepayment", "Mark Diagnostics Paid"): "Diagnostics Paid",
    ("Diagnostics Paid", "Assign Technician"): "Technician Assigned",
    ("Technician Assigned", "Start Diagnostics"): "Diagnostics In Progress",
    ("Diagnostics In Progress", "Complete Diagnosis"): "Diagnosis Completed",
    ("Diagnosis Completed", "Send Estimate"): "Estimate Sent",
    ("Estimate Sent", "Wait Client Approval"): "Waiting Client Approval",
    ("Waiting Client Approval", "Mark Parts Needed"): "Parts Needed",
    ("Waiting Client Approval", "Start Repair"): "Repair In Progress",
    ("Parts Needed", "Start Repair"): "Repair In Progress",
    ("Repair In Progress", "Complete Repair"): "Repair Completed",
    ("Repair Completed", "Send Invoice"): "Invoice Sent",
    ("Invoice Sent", "Mark Paid"): "Paid",
    ("Paid", "Activate Warranty"): "Warranty Active",
}


def find_one(client: ERPNextClient, doctype: str, field: str, value: str) -> dict[str, Any] | None:
    return client.find_one(
        doctype,
        filters=[[doctype, field, "=", value]],
        fields=["name", field],
    )


def create_or_update_by_field(
    client: ERPNextClient,
    doctype: str,
    field: str,
    value: str,
    doc: dict[str, Any],
) -> str:
    existing = find_one(client, doctype, field, value)
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


def find_repair_job_by_call_id(client: ERPNextClient, call_id: str) -> dict[str, Any] | None:
    return client.find_one(
        "Repair Job",
        filters=[["Repair Job", "zadarma_call_id", "=", call_id]],
        fields=["name", "status", "zadarma_call_id"],
    )


def first_non_group_value(client: ERPNextClient, doctype: str, preferred: str, fallback: str) -> str:
    records = client.list_docs(
        doctype,
        fields=["name", "is_group"],
        filters=[[doctype, "is_group", "=", 0]],
        limit=50,
    )
    for record in records:
        if record.get("name") == preferred:
            return preferred
    if records:
        return str(records[0]["name"])
    return fallback


def ensure_demo_employees(client: ERPNextClient, config: ERPNextConfig) -> dict[str, str]:
    employees: dict[str, str] = {}
    for item in DEMO_EMPLOYEES:
        doc = {
            "doctype": "Employee",
            "first_name": item["name"],
            "gender": "Prefer not to say",
            "date_of_birth": "1990-01-01",
            "date_of_joining": "2026-01-01",
            "status": "Active",
            "company": config.company,
            "department": item["department"],
            "designation": item["designation"],
            "cell_number": item["cell_number"],
            "ctc": item["ctc"],
            "salary_currency": "USD",
            "bio": "DEMO employee for Baro CRM leadership walkthrough.",
        }
        employee = create_or_update_by_filters(
            client,
            "Employee",
            [["Employee", "employee_name", "=", item["name"]]],
            doc,
            fields=["name", "employee_name"],
        )
        employees[item["name"]] = employee
    return employees


def ensure_demo_items(client: ERPNextClient) -> list[str]:
    items: list[str] = []
    for item in DEMO_ITEMS:
        doc = {
            "doctype": "Item",
            "item_code": item["item_code"],
            "item_name": item["item_name"],
            "item_group": "Services",
            "stock_uom": "Nos",
            "is_stock_item": 0,
            "is_sales_item": 1,
            "is_purchase_item": 0,
            "standard_rate": item["standard_rate"],
            "description": "DEMO service item for Baro CRM leadership walkthrough.",
        }
        items.append(create_or_update_by_field(client, "Item", "item_code", item["item_code"], doc))
    return items


def ensure_customer_stack(
    client: ERPNextClient,
    *,
    customer_group: str,
    territory: str,
    item: dict[str, str],
) -> tuple[str, str, str]:
    customer = create_or_update_by_field(
        client,
        "Customer",
        "customer_name",
        item["customer"],
        {
            "doctype": "Customer",
            "customer_name": item["customer"],
            "customer_type": "Company",
            "customer_group": customer_group,
            "territory": territory,
        },
    )

    contact_doc = {
        "doctype": "Contact",
        "first_name": item["contact"],
        "phone": item["phone"],
        "links": [{"link_doctype": "Customer", "link_name": customer}],
        "phone_nos": [{"phone": item["phone"], "is_primary_phone": 1}],
    }
    existing_contact = client.find_one(
        "Contact",
        filters=[["Contact", "phone", "=", item["phone"]]],
        fields=["name", "phone"],
    )
    if existing_contact:
        contact = str(existing_contact["name"])
        client.update_doc("Contact", contact, contact_doc)
    else:
        contact = str(client.create_doc("Contact", contact_doc).get("name") or item["contact"])

    address = create_or_update_by_field(
        client,
        "Address",
        "address_title",
        item["customer"][:140],
        {
            "doctype": "Address",
            "address_title": item["customer"][:140],
            "address_type": "Billing",
            "address_line1": item["address"],
            "city": item["city"],
            "state": item["state"],
            "country": "United States",
            "links": [{"link_doctype": "Customer", "link_name": customer}],
        },
    )
    return customer, contact, address


def apply_workflow_action(client: ERPNextClient, repair_job_name: str, action: str) -> str:
    doc = client.get_doc("Repair Job", repair_job_name)
    data = client._request(
        "POST",
        "/api/method/frappe.model.workflow.apply_workflow",
        payload={"doc": json.dumps(doc), "action": action},
    )
    updated_doc = dict(data.get("message") or {})
    return str(updated_doc.get("status") or updated_doc.get("workflow_state") or "")


def workflow_states_from_path(path: list[str]) -> list[str]:
    states = ["New"]
    current = "New"
    for action in path:
        current = WORKFLOW_NEXT_STATE[(current, action)]
        states.append(current)
    return states


def advance_repair_job(client: ERPNextClient, repair_job_name: str, target_status: str) -> None:
    if client.config.dry_run:
        path = WORKFLOW_PATHS.get(target_status)
        if path is None:
            print(f"WOULD SKIP workflow for {repair_job_name}: unknown target status {target_status}")
            return
        print(f"WOULD ADVANCE {repair_job_name} to {target_status}: {' -> '.join(path) or 'already New'}")
        return

    doc = client.get_doc("Repair Job", repair_job_name)
    current_status = str(doc.get("status") or "New")
    if current_status == target_status:
        return

    target_path = WORKFLOW_PATHS.get(target_status)
    if target_path is None:
        print(f"SKIP workflow for {repair_job_name}: unknown target status {target_status}")
        return

    state_path = workflow_states_from_path(target_path)
    if current_status not in state_path:
        print(
            f"SKIP workflow for {repair_job_name}: current status {current_status!r} "
            f"is not on the demo path to {target_status!r}"
        )
        return

    current_index = state_path.index(current_status)
    target_index = state_path.index(target_status)
    if current_index > target_index:
        print(
            f"SKIP workflow for {repair_job_name}: current status {current_status!r} "
            f"is already beyond demo target {target_status!r}"
        )
        return

    for action in target_path[current_index:target_index]:
        new_status = apply_workflow_action(client, repair_job_name, action)
        print(f"ADVANCED {repair_job_name}: {action} -> {new_status or 'updated'}")


def ensure_demo_repair_jobs(client: ERPNextClient, config: ERPNextConfig) -> list[str]:
    employee_map = ensure_demo_employees(client, config)
    customer_group = first_non_group_value(client, "Customer Group", "Commercial", "Commercial")
    territory = first_non_group_value(client, "Territory", "United States", "United States")
    created: list[str] = []

    for index, item in enumerate(DEMO_JOBS, start=1):
        customer, contact, address = ensure_customer_stack(
            client,
            customer_group=customer_group,
            territory=territory,
            item=item,
        )
        call_id = f"DEMO-BARO-{index:03d}"
        existing = find_repair_job_by_call_id(client, call_id)
        current_status = str(existing.get("status") or "New") if existing else "New"
        doc = {
            "doctype": "Repair Job",
            "naming_series": "RJ-.YYYY.-",
            "status": current_status,
            "customer": customer,
            "contact": contact,
            "service_address": address,
            "caller_phone": item["phone"],
            "business_phone_did": "+13479194188",
            "area": item["area"],
            "marketing_source": item["source"],
            "zadarma_recording_url": f"https://demo.baro.local/recordings/{call_id}.mp3",
            "zadarma_call_id": call_id,
            "call_datetime": f"{date.today().isoformat()} 10:{index:02d}:00",
            "call_duration_seconds": 180 + index * 12,
            "call_transcript": f"DEMO transcript for {item['customer']}: {item['purpose']}",
            "ai_call_summary": item["comment"],
            "call_quality": "Demo: clear enough to classify and route",
            "purpose_of_call": item["purpose"],
            "client_information_from_call": f"{item['contact']}--{item['customer']}",
            "service_summary": item["summary"],
            "equipment_type": item["equipment"],
            "symptom": item["summary"],
            "urgency": "Today",
            "diagnostic_price": item["diagnostic_price"],
            "prepayment_status": item["prepayment_status"],
            "technician": employee_map.get(item["technician"]) if item["technician"] else "",
            "diagnosis_result": item["diagnosis_result"],
            "estimate_amount": item["estimate_amount"],
            "client_approval_status": item["client_approval_status"],
            "parts_needed": item["parts_needed"],
            "parts_status": item["parts_status"],
            "repair_result": item["repair_result"],
            "warranty_start_date": date.today().isoformat() if item["status"] in {"Paid", "Warranty Active"} else "",
            "warranty_end_date": (date.today() + timedelta(days=30)).isoformat() if item["status"] in {"Paid", "Warranty Active"} else "",
            "next_follow_up_datetime": f"{(date.today() + timedelta(days=25)).isoformat()} 09:00:00" if item["status"] == "Warranty Active" else "",
            "internal_comment": (
                "DEMO DATA - used for leadership walkthrough.\n"
                f"Shows stage: {item['status']}.\n"
                f"Next action: {item['next_action']}\n"
                f"Story note: {item['comment']}"
            ),
        }
        if existing:
            name = str(existing["name"])
            client.update_doc("Repair Job", name, doc)
            created.append(name)
        else:
            result = client.create_doc("Repair Job", doc)
            name = str(result.get("name") or call_id)
            created.append(name)
        advance_repair_job(client, name, item["status"])

    return created


def ensure_demo_todos(client: ERPNextClient, repair_jobs: list[str]) -> list[str]:
    todo_specs = [
        ("Confirm prepayment before dispatch", "High", 1),
        ("Send ETA to client and assign technician", "High", 2),
        ("Follow up on estimate approval", "Medium", 4),
        ("Confirm parts ETA with supplier", "High", 5),
        ("Warranty care call before warranty expires", "Medium", 8),
    ]
    todos: list[str] = []
    owner = client.ping() if not client.config.dry_run else "Administrator"
    for description, priority, job_index in todo_specs:
        if job_index > len(repair_jobs):
            continue
        repair_job = repair_jobs[job_index - 1]
        marker = f"DEMO-TODO-{job_index:03d}"
        doc = {
            "doctype": "ToDo",
            "status": "Open",
            "priority": priority,
            "date": (date.today() + timedelta(days=1)).isoformat(),
            "allocated_to": owner,
            "description": f"{marker}: {description}",
            "reference_type": "Repair Job",
            "reference_name": repair_job,
        }
        todos.append(
            create_or_update_by_filters(
                client,
                "ToDo",
                [
                    ["ToDo", "reference_type", "=", "Repair Job"],
                    ["ToDo", "reference_name", "=", repair_job],
                    ["ToDo", "description", "like", f"{marker}%"],
                ],
                doc,
                fields=["name", "description"],
            )
        )
    return todos


def ensure_demo_invoice(client: ERPNextClient, config: ERPNextConfig, project: str) -> str | None:
    try:
        customer = find_one(client, "Customer", "customer_name", "DEMO - Sarasota Hotel Kitchen")
        if not customer:
            return None
        remarks = "DEMO-BARO-INVOICE-001 - paid dishwasher repair example"
        doc = {
            "doctype": "Sales Invoice",
            "company": config.company,
            "naming_series": "ACC-SINV-.YYYY.-",
            "customer": customer["name"],
            "posting_date": date.today().isoformat(),
            "due_date": date.today().isoformat(),
            "project": project,
            "currency": "USD",
            "conversion_rate": 1,
            "selling_price_list": "Standard Selling",
            "price_list_currency": "USD",
            "plc_conversion_rate": 1,
            "debit_to": "Debtors - BSL",
            "cost_center": "Main - BSL",
            "remarks": remarks,
            "items": [
                {
                    "doctype": "Sales Invoice Item",
                    "item_code": "DEMO-DIAGNOSTIC-SERVICE",
                    "item_name": "DEMO - Diagnostic Service Call",
                    "description": "Diagnostic service call credited toward repair",
                    "qty": 1,
                    "uom": "Nos",
                    "conversion_factor": 1,
                    "rate": 159,
                    "amount": 159,
                    "income_account": "Service - BSL",
                    "cost_center": "Main - BSL",
                },
                {
                    "doctype": "Sales Invoice Item",
                    "item_code": "DEMO-REPAIR-LABOR",
                    "item_name": "DEMO - Repair Labor",
                    "description": "Dishwasher drain pump replacement labor",
                    "qty": 1,
                    "uom": "Nos",
                    "conversion_factor": 1,
                    "rate": 361,
                    "amount": 361,
                    "income_account": "Service - BSL",
                    "cost_center": "Main - BSL",
                },
            ],
        }
        return create_or_update_by_field(client, "Sales Invoice", "remarks", remarks, doc)
    except ERPNextError as exc:
        print(f"SKIP demo Sales Invoice: {exc}")
        return None


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


def ensure_kanban(client: ERPNextClient) -> str:
    name = "Baro Repair Job Pipeline"
    existing = find_one(client, "Kanban Board", "kanban_board_name", name)
    doc = {
        "doctype": "Kanban Board",
        "kanban_board_name": name,
        "reference_doctype": "Repair Job",
        "field_name": "status",
        "private": 0,
        "show_labels": 1,
        "columns": [
            {"column_name": status, "status": "Active", "indicator": color}
            for status, color in REPAIR_JOB_STATUSES
        ],
        "filters": json.dumps([]),
        "fields": json.dumps(["customer", "area", "marketing_source", "equipment_type", "caller_phone"]),
    }
    if existing:
        client.update_doc("Kanban Board", str(existing["name"]), doc)
        return str(existing["name"])
    result = client.create_doc("Kanban Board", doc)
    return str(result.get("name") or name)


def ensure_demo_project(client: ERPNextClient, config: ERPNextConfig) -> str:
    project_name = "DEMO - Marriott Residence Inn Client Work Group"
    project = create_or_update_by_field(
        client,
        "Project",
        "project_name",
        project_name,
        {
            "doctype": "Project",
            "naming_series": "PROJ-.####",
            "project_name": project_name,
            "status": "Open",
            "priority": "High",
            "company": config.company,
            "expected_start_date": date.today().isoformat(),
            "expected_end_date": (date.today() + timedelta(days=3)).isoformat(),
            "notes": "DEMO project showing the client work group around one repair job.",
        },
    )
    tasks = [
        ("DEMO - Confirm ETA and payment method", "Open"),
        ("DEMO - Dispatch technician and update client", "Open"),
        ("DEMO - Review diagnosis and prepare estimate", "Open"),
        ("DEMO - Warranty follow-up after completion", "Open"),
    ]
    for subject, status in tasks:
        create_or_update_by_field(
            client,
            "Task",
            "subject",
            subject,
            {
                "doctype": "Task",
                "subject": subject,
                "status": status,
                "priority": "High" if "Dispatch" in subject else "Medium",
                "project": project,
                "description": "DEMO task for leadership walkthrough of client group automation.",
                "exp_start_date": date.today().isoformat(),
                "exp_end_date": (date.today() + timedelta(days=1)).isoformat(),
            },
        )
    return project


def ensure_workspace(client: ERPNextClient, number_cards: list[str], kanban_name: str) -> str:
    workspace_name = "Baro CRM Demo"
    shortcuts = [
        {"type": "DocType", "link_to": "Repair Job", "doc_view": "List", "label": "All Repair Jobs", "icon": "list"},
        {"type": "DocType", "link_to": "Repair Job", "doc_view": "Kanban", "kanban_board": kanban_name, "label": "Repair Pipeline", "icon": "kanban"},
        {"type": "DocType", "link_to": "Customer", "doc_view": "List", "label": "Customer Cards", "icon": "customer"},
        {"type": "DocType", "link_to": "Project", "doc_view": "List", "label": "Client Work Groups", "icon": "project"},
        {"type": "DocType", "link_to": "Task", "doc_view": "List", "label": "Team Tasks", "icon": "task"},
        {"type": "DocType", "link_to": "ToDo", "doc_view": "List", "label": "Follow-up ToDos", "icon": "check"},
        {"type": "DocType", "link_to": "Employee", "doc_view": "List", "label": "Team / Employees", "icon": "users"},
        {"type": "DocType", "link_to": "Item", "doc_view": "List", "label": "Service Items", "icon": "item"},
        {"type": "DocType", "link_to": "Sales Invoice", "doc_view": "List", "label": "Invoices", "icon": "money"},
    ]
    links = [
        {"type": "Card Break", "label": "Client History"},
        {"type": "Link", "label": "Customer", "link_type": "DocType", "link_to": "Customer", "onboard": 1},
        {"type": "Link", "label": "Contact", "link_type": "DocType", "link_to": "Contact", "onboard": 1},
        {"type": "Link", "label": "Address", "link_type": "DocType", "link_to": "Address", "onboard": 1},
        {"type": "Card Break", "label": "Repair Operations"},
        {"type": "Link", "label": "Repair Job", "link_type": "DocType", "link_to": "Repair Job", "onboard": 1},
        {"type": "Link", "label": "Project", "link_type": "DocType", "link_to": "Project", "onboard": 1},
        {"type": "Link", "label": "Task", "link_type": "DocType", "link_to": "Task", "onboard": 1},
        {"type": "Link", "label": "ToDo", "link_type": "DocType", "link_to": "ToDo", "onboard": 1},
        {"type": "Card Break", "label": "Money and Warranty"},
        {"type": "Link", "label": "Sales Invoice", "link_type": "DocType", "link_to": "Sales Invoice", "onboard": 1},
        {"type": "Link", "label": "Payment Entry", "link_type": "DocType", "link_to": "Payment Entry", "onboard": 1},
        {"type": "Card Break", "label": "Team and Roles"},
        {"type": "Link", "label": "Employee", "link_type": "DocType", "link_to": "Employee", "onboard": 1},
        {"type": "Link", "label": "Timesheet", "link_type": "DocType", "link_to": "Timesheet", "onboard": 1},
        {"type": "Link", "label": "Role Profile", "link_type": "DocType", "link_to": "Role Profile", "onboard": 1},
    ]
    quick_lists = [
        {
            "document_type": "Repair Job",
            "label": "New Repair Jobs",
            "quick_list_filter": json.dumps([["Repair Job", "status", "=", "New"]]),
        },
        {
            "document_type": "Repair Job",
            "label": "Needs Follow-up",
            "quick_list_filter": json.dumps([["Repair Job", "status", "in", ["Need Follow-up", "Waiting Prepayment", "Waiting Client Approval"]]]),
        },
        {
            "document_type": "Repair Job",
            "label": "Active Repairs",
            "quick_list_filter": json.dumps([["Repair Job", "status", "in", ["Technician Assigned", "Diagnostics In Progress", "Repair In Progress"]]]),
        },
    ]
    content = [
        {"id": "baro-demo-header", "type": "header", "data": {"text": "<span class=\"h4\"><b>Baro Service CRM Demo</b></span><br>Call -> customer card -> diagnostic -> technician -> estimate -> repair -> payment -> warranty", "col": 12}},
        *[
            {"id": f"baro-card-{index}", "type": "number_card", "data": {"number_card_name": card, "col": 4}}
            for index, card in enumerate(number_cards, start=1)
        ],
        {"id": "baro-demo-spacer", "type": "spacer", "data": {"col": 12}},
        {"id": "baro-client-card", "type": "card", "data": {"card_name": "Client History", "col": 4}},
        {"id": "baro-ops-card", "type": "card", "data": {"card_name": "Repair Operations", "col": 4}},
        {"id": "baro-money-card", "type": "card", "data": {"card_name": "Money and Warranty", "col": 4}},
        {"id": "baro-team-card", "type": "card", "data": {"card_name": "Team and Roles", "col": 4}},
    ]
    doc = {
        "doctype": "Workspace",
        "label": workspace_name,
        "title": workspace_name,
        "module": "Custom",
        "type": "Workspace",
        "public": 1,
        "is_hidden": 0,
        "icon": "crm",
        "indicator_color": "blue",
        "content": json.dumps(content),
        "shortcuts": shortcuts,
        "links": links,
        "quick_lists": quick_lists,
        "number_cards": [{"number_card_name": card, "label": card} for card in number_cards],
    }
    existing = find_one(client, "Workspace", "label", workspace_name)
    if existing:
        client.update_doc("Workspace", str(existing["name"]), doc)
        return str(existing["name"])
    result = client.create_doc("Workspace", doc)
    return str(result.get("name") or workspace_name)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a polished Baro CRM demo environment in ERPNext.")
    parser.add_argument("--execute", action="store_true", help="Actually write demo records. Default is dry-run.")
    args = parser.parse_args()

    config = ERPNextConfig.from_env()
    if args.execute:
        config = replace(config, dry_run=False)
    client = ERPNextClient(config)

    print(f"ERPNext site: {config.base_url}")
    print(f"Mode: {'EXECUTE' if args.execute else 'DRY RUN'}")

    number_cards = [
        ensure_number_card(client, "Baro Open Repair Jobs", [["Repair Job", "status", "not in", ["Paid", "Closed", "Lost", "Spam", "Unrelated"]]]),
        ensure_number_card(client, "Baro Needs Follow-up", [["Repair Job", "status", "in", ["Need Follow-up", "Waiting Prepayment", "Waiting Client Approval"]]]),
        ensure_number_card(client, "Baro Active Repairs", [["Repair Job", "status", "in", ["Technician Assigned", "Diagnostics In Progress", "Repair In Progress"]]]),
    ]
    kanban = ensure_kanban(client)
    items = ensure_demo_items(client)
    repair_jobs = ensure_demo_repair_jobs(client, config)
    project = ensure_demo_project(client, config)
    todos = ensure_demo_todos(client, repair_jobs)
    invoice = ensure_demo_invoice(client, config, project)
    workspace = ensure_workspace(client, number_cards, kanban)

    print(json.dumps(
        {
            "workspace": workspace,
            "kanban": kanban,
            "number_cards": number_cards,
            "demo_items": items,
            "demo_repair_jobs": repair_jobs,
            "demo_project": project,
            "demo_todos": todos,
            "demo_invoice": invoice,
        },
        indent=2,
        ensure_ascii=False,
    ))

    if not args.execute:
        print("Dry run complete. Re-run with --execute to create/update the demo environment.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
