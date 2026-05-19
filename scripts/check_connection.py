from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from erpnext_client import ERPNextConfig, ERPNextError, get_client


def main() -> int:
    config = ERPNextConfig.from_env()
    client = get_client()
    print(f"ERPNext site: {config.base_url}")
    print(f"Company: {config.company}")
    print(f"Dry run: {config.dry_run}")
    print("API key loaded: yes")
    try:
        user = client.ping()
        print(f"Connected as: {user}")
        company = client.get_doc("Company", config.company)
        print(f"Company visible: {company.get('name')}")
    except ERPNextError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
