from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from erpnext_client import ERPNextClient, ERPNextConfig, ERPNextError


ROLE_PROFILES: dict[str, list[str]] = {
    "Baro Estimate Manager": ["Sales User", "Sales Manager", "Support Team", "Maintenance User", "Employee"],
    "Baro Regular Client Manager": ["Sales User", "Sales Manager", "Support Team", "Maintenance User", "Employee"],
    "Baro Production Manager": ["Maintenance Manager", "Maintenance User", "Projects Manager", "Projects User", "Employee"],
    "Baro Technician": ["Maintenance User", "Projects User", "Employee"],
    "Baro Supply": ["Purchase User", "Stock User", "Item Manager", "Employee"],
    "Baro Accounting": ["Accounts User", "Sales User", "Employee"],
    "Baro Admin Owner": ["System Manager", "Sales Manager", "Accounts Manager", "Stock Manager", "Purchase Manager", "Report Manager", "Workspace Manager"],
}


def profile_exists(client: ERPNextClient, name: str) -> bool:
    return bool(client.find_by_field("Role Profile", "name", name, limit=1))


def role_exists(client: ERPNextClient, name: str) -> bool:
    return bool(client.find_by_field("Role", "name", name, limit=1))


def profile_payload(name: str, roles: list[str]) -> dict:
    return {
        "doctype": "Role Profile",
        "role_profile": name,
        "roles": [{"doctype": "Has Role", "role": role} for role in roles],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create Baro ERPNext Role Profiles.")
    parser.add_argument("--execute", action="store_true", help="Actually create missing profiles. Default is dry-run.")
    args = parser.parse_args()

    config = ERPNextConfig.from_env()
    if args.execute:
        config = replace(config, dry_run=False)
    client = ERPNextClient(config)

    print(f"ERPNext site: {config.base_url}")
    print(f"Mode: {'EXECUTE' if args.execute else 'DRY RUN'}")

    created = 0
    skipped = 0
    for name, roles in ROLE_PROFILES.items():
        missing_roles = [role for role in roles if not role_exists(client, role)]
        if missing_roles:
            print(f"SKIP {name}: missing roles {missing_roles}")
            skipped += 1
            continue
        if profile_exists(client, name):
            print(f"EXISTS {name}")
            skipped += 1
            continue
        payload = profile_payload(name, roles)
        if not args.execute:
            print(f"WOULD CREATE {name}: {roles}")
            continue
        result = client.create_doc("Role Profile", payload)
        print(f"CREATED {result.get('name') or name}: {roles}")
        created += 1

    print(f"Done. Created: {created}. Skipped/existing: {skipped}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())