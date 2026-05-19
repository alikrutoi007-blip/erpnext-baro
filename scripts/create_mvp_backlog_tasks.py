from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from erpnext_client import ERPNextClient, ERPNextConfig


PROJECT_NAME = "Baro CRM MVP Implementation"

TASKS = [
    {
        "subject": "Automation: create client group for every qualified new lead",
        "description": (
            "When a new qualified lead/Repair Job is created, create or find a linked "
            "Project work group named by client/business name, area, and Repair Job ID. "
            "Add default tasks/ToDos for Dispatcher/ID, Estimate Manager, Production "
            "Manager, Regular Client Manager, and ROP. Add Technician after assignment, "
            "Supply when parts are needed, and Accounting when invoice/payment starts. "
            "Do not create groups for Spam, Unrelated, wrong number, or no-service-intent calls. "
            "Implementation must be idempotent using Repair Job.client_group_project."
        ),
    },
    {
        "subject": "Connect Zadarma/Google Sheets bot to ERPNext Repair Job",
        "description": (
            "Map enriched call rows into Customer, Contact, Address, and Repair Job. "
            "Use Zadarma recording URL/call ID as idempotency key. Store transcript, "
            "quality, purpose, source, area, address, service summary, and comments."
        ),
    },
    {
        "subject": "Create first leadership demo flow in ERPNext",
        "description": (
            "Show one real customer journey: incoming call, transcript, Repair Job, "
            "diagnostic/prepayment, technician assignment, diagnosis, estimate, repair, "
            "invoice/payment, and warranty follow-up."
        ),
    },
]


def find_by_name(client: ERPNextClient, doctype: str, fieldname: str, value: str) -> str | None:
    matches = client.find_by_field(doctype, fieldname, value, limit=1)
    if not matches:
        return None
    return str(matches[0]["name"])


def ensure_project(client: ERPNextClient, company: str) -> str:
    existing = find_by_name(client, "Project", "project_name", PROJECT_NAME)
    if existing:
        print(f"EXISTS Project: {PROJECT_NAME} ({existing})")
        return existing

    doc = {
        "doctype": "Project",
        "naming_series": "PROJ-.####",
        "project_name": PROJECT_NAME,
        "company": company,
        "status": "Open",
    }
    created = client.create_doc("Project", doc)
    name = str(created.get("name") or PROJECT_NAME)
    print(f"CREATED Project: {PROJECT_NAME} ({name})")
    return name


def task_exists(client: ERPNextClient, subject: str, project_name: str) -> bool:
    matches = client.list_docs(
        "Task",
        fields=["name", "subject", "project"],
        filters=[["Task", "subject", "=", subject], ["Task", "project", "=", project_name]],
        limit=1,
    )
    return bool(matches)


def ensure_tasks(client: ERPNextClient, project_name: str) -> tuple[int, int]:
    created_count = 0
    skipped_count = 0
    for task in TASKS:
        subject = task["subject"]
        if task_exists(client, subject, project_name):
            print(f"EXISTS Task: {subject}")
            skipped_count += 1
            continue
        doc = {
            "doctype": "Task",
            "subject": subject,
            "project": project_name,
            "status": "Open",
            "priority": "High" if "client group" in subject.lower() else "Medium",
            "description": task["description"],
        }
        created = client.create_doc("Task", doc)
        print(f"CREATED Task: {created.get('name') or subject}")
        created_count += 1
    return created_count, skipped_count


def main() -> int:
    parser = argparse.ArgumentParser(description="Create Baro CRM MVP backlog Project and Tasks.")
    parser.add_argument("--execute", action="store_true", help="Actually create records. Default is dry-run.")
    args = parser.parse_args()

    config = ERPNextConfig.from_env()
    if args.execute:
        config = replace(config, dry_run=False)
    client = ERPNextClient(config)

    print(f"ERPNext site: {config.base_url}")
    print(f"Mode: {'EXECUTE' if args.execute else 'DRY RUN'}")

    project_name = ensure_project(client, config.company)
    created, skipped = ensure_tasks(client, project_name)
    print(f"Done. Tasks created: {created}. Skipped/existing: {skipped}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
