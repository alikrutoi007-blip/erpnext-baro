#!/usr/bin/env python
"""K live smoke. Runs migrate_customers against a tiny generated CSV on the live
site: dry-run, then execute, then verifies dedup recognition, then rolls back.

All records carry a per-run TEST-K-* prefix and a unique import_batch_id, so
cleanup is exact. Requires ERPNEXT_DRY_RUN=0 + --execute to write.
"""
import argparse
import io
import sys
import uuid
import random
from datetime import date
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from erpnext_client import get_client, ERPNextError  # noqa: E402
import migrate_customers as mc  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--keep", action="store_true", help="Skip rollback at the end.")
    args = parser.parse_args()

    client = get_client()
    if args.execute and client.config.dry_run:
        print("Set ERPNEXT_DRY_RUN=0 to run --execute writes.")
        sys.exit(1)

    call = mc._make_call(client)
    run_id = "TEST-K-%s-%s" % (date.today().strftime("%Y%m%d"), uuid.uuid4().hex[:8])
    phone = "+1212559" + "".join(random.choices("0123456789", k=4))
    batch_id = run_id
    print("Run prefix : %s\nTest phone : %s\nBatch      : %s\n" % (run_id, phone, batch_id))

    csv_text = (
        "legacy_customer_id,customer_name,caller_phone_raw,area,service_state,"
        "marketing_source,first_contact_date,last_known_equipment,notes\n"
        "%s-A,%s Sunrise Diner,%s,Brooklyn,,Google,2023-01-01,Combi Oven,smoke A\n"
        "%s-B,%s No Phone Co,,Austin TX,,Referral,2022-05-05,Fryer,smoke B\n"
        % (run_id, run_id, phone, run_id, run_id)
    )
    rows = mc.parse_csv_text(csv_text)
    failures = []

    def check(name, fn):
        try:
            fn(); print("  OK   %s" % name)
        except Exception as e:
            failures.append((name, e)); print("  FAIL %s: %s" % (name, e))

    # 1. Dry-run writes nothing
    def t1():
        s = mc.run_migration(client, rows, source_system="smoke",
                             batch_id=batch_id + "-dry", execute=False)
        assert s["written"] == 0, "dry-run wrote %d" % s["written"]
        assert s["insert_new"] >= 1
        assert s["insert_with_warning"] >= 1  # the no-phone row
    check("dry-run classifies, writes nothing", t1)

    if not args.execute:
        print("\n(dry-run only — pass --execute to test writes + rollback)")
        _report(failures); return

    # 2. Execute creates customers + contact
    created_phone_customer = []
    def t2():
        s = mc.run_migration(client, rows, source_system="smoke",
                             batch_id=batch_id, execute=True)
        assert s["written"] == 2, "expected 2 writes, got %d" % s["written"]
        assert s["failures"] == 0
        custs = client.list_docs("Customer",
            filters=[["import_batch_id", "=", batch_id]], fields=["name"], limit=10)
        assert len(custs) == 2, "expected 2 customers, got %d" % len(custs)
    check("execute creates 2 customers", t2)

    # 3. F dedup helper now recognizes the imported phone
    def t3():
        ids = call("baro_crm.api.customer_migration.find_customers_by_phone",
                   {"phone": phone})
        assert ids, "imported phone not found by dedup helper"
        created_phone_customer.append(ids[0])
    check("dedup helper finds imported phone", t3)

    # 4. Re-run execute is idempotent (0 new writes via legacy_customer_id skip)
    def t4():
        s = mc.run_migration(client, rows, source_system="smoke",
                             batch_id=batch_id, execute=True)
        assert s["skip_already_imported"] == 2, \
            "expected 2 skips on re-run, got %d" % s["skip_already_imported"]
        assert s["written"] == 0
    check("re-run is idempotent (0 new writes)", t4)

    # 5. Rollback: two-step token
    def t5():
        step1 = call("baro_crm.api.customer_migration.rollback_batch",
                     {"batch_id": batch_id})
        assert step1["requires_confirmation"] is True
        assert step1["customer_count"] == 2
        token = step1["confirm_token"]
        step2 = call("baro_crm.api.customer_migration.rollback_batch",
                     {"batch_id": batch_id, "confirm_token": token})
        assert step2["ok"] is True
        assert step2["deleted_count"] == 2, "deleted %d" % step2["deleted_count"]
        left = client.list_docs("Customer",
            filters=[["import_batch_id", "=", batch_id]], fields=["name"], limit=10)
        assert not left, "rollback left %d customers" % len(left)
    if not args.keep:
        check("rollback two-step removes the batch", t5)

    _report(failures)


def _report(failures):
    if failures:
        print("\n%d failure(s):" % len(failures))
        for name, e in failures:
            print("  - %s: %s" % (name, e))
        sys.exit(1)
    print("\nAll K smoke checks passed.")


if __name__ == "__main__":
    main()
