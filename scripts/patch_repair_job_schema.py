from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from erpnext_client import ERPNextClient, ERPNextConfig


PATCHES: dict[str, dict[str, Any]] = {
    "zadarma_recording_url": {
        "fieldtype": "Small Text",
        "unique": 0,
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch existing Repair Job DocType fields safely.")
    parser.add_argument("--execute", action="store_true", help="Actually update ERPNext. Default is dry-run.")
    args = parser.parse_args()

    config = ERPNextConfig.from_env()
    if args.execute:
        config = replace(config, dry_run=False)
    client = ERPNextClient(config)

    doc = client.get_doc("DocType", "Repair Job")
    changed: list[str] = []

    for field in doc.get("fields", []):
        fieldname = field.get("fieldname")
        if fieldname not in PATCHES:
            continue
        for key, value in PATCHES[fieldname].items():
            if field.get(key) != value:
                field[key] = value
                changed.append(f"{fieldname}.{key} -> {value}")

    print(f"ERPNext site: {config.base_url}")
    print(f"Mode: {'EXECUTE' if args.execute else 'DRY RUN'}")
    if not changed:
        print("No Repair Job schema changes needed.")
        return 0

    print("Planned changes:")
    for item in changed:
        print(f"- {item}")

    if not args.execute:
        print("Dry run complete. Re-run with --execute to patch ERPNext.")
        return 0

    updated = client.update_doc("DocType", "Repair Job", doc)
    print(f"Updated DocType: {updated.get('name', 'Repair Job')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
