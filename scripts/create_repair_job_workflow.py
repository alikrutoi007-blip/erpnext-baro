from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from erpnext_client import ERPNextClient, ERPNextConfig, ERPNextError


WORKFLOW_NAME = "Repair Job Workflow"
DOCTYPE = "Repair Job"
STATE_FIELD = "status"

STATE_STYLES = {
    "New": "Info",
    "Need Follow-up": "Warning",
    "Diagnostics Offered": "Info",
    "Waiting Prepayment": "Warning",
    "Diagnostics Paid": "Success",
    "Technician Assigned": "Primary",
    "Diagnostics In Progress": "Primary",
    "Diagnosis Completed": "Success",
    "Estimate Sent": "Info",
    "Waiting Client Approval": "Warning",
    "Parts Needed": "Warning",
    "Repair In Progress": "Primary",
    "Repair Completed": "Success",
    "Invoice Sent": "Info",
    "Paid": "Success",
    "Warranty Active": "Info",
    "Closed": "Inverse",
    "Lost": "Danger",
    "Spam": "Danger",
    "Unrelated": "Inverse",
}

STATE_EDIT_ROLE = {
    "New": "Support Team",
    "Need Follow-up": "Support Team",
    "Diagnostics Offered": "Sales User",
    "Waiting Prepayment": "Sales User",
    "Diagnostics Paid": "Sales Manager",
    "Technician Assigned": "Maintenance Manager",
    "Diagnostics In Progress": "Maintenance User",
    "Diagnosis Completed": "Maintenance Manager",
    "Estimate Sent": "Sales Manager",
    "Waiting Client Approval": "Sales User",
    "Parts Needed": "Maintenance Manager",
    "Repair In Progress": "Maintenance User",
    "Repair Completed": "Maintenance Manager",
    "Invoice Sent": "Accounts User",
    "Paid": "Accounts User",
    "Warranty Active": "Support Team",
    "Closed": "Sales Manager",
    "Lost": "Sales Manager",
    "Spam": "Support Team",
    "Unrelated": "Support Team",
}

TRANSITIONS = [
    ("New", "Mark Need Follow-up", "Need Follow-up", "Support Team"),
    ("New", "Offer Diagnostics", "Diagnostics Offered", "Sales User"),
    ("New", "Mark Lost", "Lost", "Sales Manager"),
    ("New", "Mark Spam", "Spam", "Support Team"),
    ("New", "Mark Unrelated", "Unrelated", "Support Team"),
    ("Need Follow-up", "Offer Diagnostics", "Diagnostics Offered", "Sales User"),
    ("Need Follow-up", "Mark Lost", "Lost", "Sales Manager"),
    ("Need Follow-up", "Mark Unrelated", "Unrelated", "Support Team"),
    ("Diagnostics Offered", "Request Prepayment", "Waiting Prepayment", "Sales User"),
    ("Diagnostics Offered", "Mark Diagnostics Paid", "Diagnostics Paid", "Sales User"),
    ("Diagnostics Offered", "Mark Lost", "Lost", "Sales Manager"),
    ("Waiting Prepayment", "Mark Diagnostics Paid", "Diagnostics Paid", "Sales User"),
    ("Waiting Prepayment", "Mark Need Follow-up", "Need Follow-up", "Support Team"),
    ("Waiting Prepayment", "Mark Lost", "Lost", "Sales Manager"),
    ("Diagnostics Paid", "Assign Technician", "Technician Assigned", "Maintenance Manager"),
    ("Technician Assigned", "Start Diagnostics", "Diagnostics In Progress", "Maintenance User"),
    ("Diagnostics In Progress", "Complete Diagnosis", "Diagnosis Completed", "Maintenance User"),
    ("Diagnosis Completed", "Send Estimate", "Estimate Sent", "Sales Manager"),
    ("Estimate Sent", "Wait Client Approval", "Waiting Client Approval", "Sales User"),
    ("Waiting Client Approval", "Mark Parts Needed", "Parts Needed", "Maintenance Manager"),
    ("Waiting Client Approval", "Start Repair", "Repair In Progress", "Maintenance Manager"),
    ("Waiting Client Approval", "Mark Lost", "Lost", "Sales Manager"),
    ("Parts Needed", "Start Repair", "Repair In Progress", "Maintenance Manager"),
    ("Repair In Progress", "Complete Repair", "Repair Completed", "Maintenance User"),
    ("Repair Completed", "Send Invoice", "Invoice Sent", "Accounts User"),
    ("Invoice Sent", "Mark Paid", "Paid", "Accounts User"),
    ("Paid", "Activate Warranty", "Warranty Active", "Sales Manager"),
    ("Warranty Active", "Close Job", "Closed", "Sales Manager"),
]


def exists(client: ERPNextClient, doctype: str, name: str) -> bool:
    try:
        client.get_doc(doctype, name)
        return True
    except ERPNextError as exc:
        if "HTTP 404" in str(exc):
            return False
        raise


def create_if_missing(client: ERPNextClient, doctype: str, name: str, payload: dict[str, Any], execute: bool) -> bool:
    if exists(client, doctype, name):
        print(f"EXISTS {doctype}: {name}")
        return False
    if not execute:
        print(f"WOULD CREATE {doctype}: {name}")
        return False
    result = client.create_doc(doctype, payload)
    print(f"CREATED {doctype}: {result.get('name') or name}")
    return True


def workflow_payload() -> dict[str, Any]:
    states = [
        {
            "doctype": "Workflow Document State",
            "state": state,
            "doc_status": "0",
            "allow_edit": STATE_EDIT_ROLE[state],
        }
        for state in STATE_STYLES
    ]
    transitions = [
        {
            "doctype": "Workflow Transition",
            "state": state,
            "action": action,
            "next_state": next_state,
            "allowed": allowed,
            "allow_self_approval": 1,
        }
        for state, action, next_state, allowed in TRANSITIONS
    ]
    return {
        "doctype": "Workflow",
        "workflow_name": WORKFLOW_NAME,
        "document_type": DOCTYPE,
        "is_active": 1,
        "override_status": 1,
        "send_email_alert": 0,
        "workflow_state_field": STATE_FIELD,
        "states": states,
        "transitions": transitions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create Repair Job workflow in ERPNext.")
    parser.add_argument("--execute", action="store_true", help="Actually create states/actions/workflow. Default is dry-run.")
    args = parser.parse_args()

    config = ERPNextConfig.from_env()
    if args.execute:
        config = replace(config, dry_run=False)
    client = ERPNextClient(config)

    print(f"ERPNext site: {config.base_url}")
    print(f"Workflow: {WORKFLOW_NAME}")
    print(f"Mode: {'EXECUTE' if args.execute else 'DRY RUN'}")

    created_count = 0
    for state, style in STATE_STYLES.items():
        payload = {
            "doctype": "Workflow State",
            "workflow_state_name": state,
            "style": style,
        }
        created_count += int(create_if_missing(client, "Workflow State", state, payload, args.execute))

    actions = sorted({action for _state, action, _next_state, _allowed in TRANSITIONS})
    for action in actions:
        payload = {
            "doctype": "Workflow Action Master",
            "workflow_action_name": action,
        }
        created_count += int(create_if_missing(client, "Workflow Action Master", action, payload, args.execute))

    if exists(client, "Workflow", WORKFLOW_NAME):
        print(f"EXISTS Workflow: {WORKFLOW_NAME}")
    else:
        if not args.execute:
            print(f"WOULD CREATE Workflow: {WORKFLOW_NAME}")
        else:
            result = client.create_doc("Workflow", workflow_payload())
            print(f"CREATED Workflow: {result.get('name') or WORKFLOW_NAME}")
            created_count += 1

    print(f"Done. Created records: {created_count}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
