#!/usr/bin/env python
"""Existing Customer Migration (K).

Imports scattered legacy customers into ERPNext as normalized, dedup-safe
Customer + Contact records. Default mode is dry-run; pass --execute to write.

Pure decision logic lives at module top and is unit-tested without a server
(tests/test_migrate_customers.py). The ERPNext REST client is imported lazily
inside main() so importing this module never requires .env or the network.

Usage:
  python scripts/migrate_customers.py --input data.csv --source-system legacy_sheet
  python scripts/migrate_customers.py --input data.csv --source-system legacy_sheet --execute
"""
from __future__ import annotations

import csv
import io
import re

# ---------------------------------------------------------------------------
# Pure logic (no I/O) — unit-tested
# ---------------------------------------------------------------------------

# Order matters: first match wins when an area mentions more than one state.
# Texas is listed first as the primary service territory; reorder with care.
# Canonical state -> keyword tokens. Two-letter codes are matched as whole
# tokens; multi-word names match as substrings.
STATE_KEYWORDS = [
    ("Texas", ("tx", "texas", "houston", "dallas", "austin",
               "san antonio", "fort worth", "el paso")),
    ("Florida", ("fl", "florida", "miami", "orlando", "tampa",
                 "jacksonville", "fort lauderdale")),
    ("New York", ("ny", "new york", "nyc", "manhattan", "brooklyn",
                  "queens", "bronx", "staten island")),
    ("New Jersey", ("nj", "new jersey", "newark", "jersey city",
                    "trenton", "elizabeth")),
]
_CANON_STATES = {c for c, _ in STATE_KEYWORDS}


def normalize_phone_local(raw):
    """Mirror of baro_crm.api.repair_job.normalize_phone. Returns '+<digits>' or ''."""
    if not raw:
        return ""
    digits = re.sub(r"\D", "", str(raw))
    if not digits:
        return ""
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return "+" + digits


def infer_service_state(area="", explicit_state=""):
    """Return one of Texas/Florida/New York/New Jersey, or '' when unknown.
    An explicit (valid) state wins; otherwise infer from the area string."""
    e = (explicit_state or "").strip()
    if e:
        if e in _CANON_STATES:           # already a canonical state name
            return e
        el = e.casefold()
        for canon, kws in STATE_KEYWORDS:
            if el == canon.casefold() or el in kws:
                return canon
    # If explicit_state is non-empty but outside our 4-state scope, treat it as
    # unknown and fall through to area inference.
    a = (area or "").casefold()
    if a:
        tokens = set(re.split(r"[^a-z]+", a))
        for canon, kws in STATE_KEYWORDS:
            for kw in kws:
                if len(kw) == 2:
                    if kw in tokens:        # whole-token match for bare codes
                        return canon
                elif kw in a:               # substring for multi-word names
                    return canon
    return ""


# Fields compared to decide "conflict" vs "fill blank" on a single phone match.
COMPARE_FIELDS = ("customer_name", "city_area", "service_state",
                  "last_known_equipment", "first_seen")


def build_write_fields(row, source_system="", batch_id=""):
    """Resolve a raw CSV row into the Customer fields we intend to write."""
    # Note: 'notes' and 'marketing_source' are intentionally not returned here.
    # The write layer folds them into a Customer Comment at import time.
    return {
        "customer_name": (row.get("customer_name") or "").strip(),
        "normalized_phone": normalize_phone_local(row.get("caller_phone_raw")),
        "legacy_customer_id": (row.get("legacy_customer_id") or "").strip(),
        "source_system": source_system,
        "import_batch_id": batch_id,
        "city_area": (row.get("area") or "").strip(),
        "service_state": infer_service_state(row.get("area", ""),
                                             row.get("service_state", "")),
        "first_seen": (row.get("first_contact_date") or "").strip(),
        "last_known_equipment": (row.get("last_known_equipment") or "").strip(),
    }


def values_conflict(csv_value, existing_value):
    """True only when BOTH are non-empty AND differ after casefold+strip."""
    a = (csv_value or "").strip()
    b = (existing_value or "").strip()
    if not a or not b:
        return False
    return a.casefold() != b.casefold()


def detect_field_conflicts(write_fields, existing):
    """List of conflicting compare-fields between the CSV row and an existing Customer."""
    conflicts = []
    for f in COMPARE_FIELDS:
        cv, ev = write_fields.get(f, ""), existing.get(f, "")
        if values_conflict(cv, ev):
            conflicts.append({"field": f, "csv_value": cv, "existing_value": ev})
    return conflicts


def classify_row(write_fields, *, phone_norm, legacy_exists,
                 phone_match_ids, existing_customer, name_match_id):
    """Spec section 4 decision engine. Pure: caller supplies lookup results.

    Returns a dict with at least 'decision', 'reason', 'conflict_type'.
    Decisions: skip_already_imported | insert_new | update_missing_only |
    conflict_skip | conflict_multi_phone | conflict_name_only | insert_with_warning
    """
    if legacy_exists:
        return {"decision": "skip_already_imported",
                "reason": "legacy_customer_id already imported", "conflict_type": None}

    if phone_norm:
        n = len(phone_match_ids)
        if n == 0:
            return {"decision": "insert_new", "reason": "no phone match",
                    "conflict_type": None}
        if n == 1:
            if existing_customer is None:
                raise ValueError(
                    "existing_customer must be provided when phone_match_ids has one entry")
            conflicts = detect_field_conflicts(write_fields, existing_customer)
            if conflicts:
                return {"decision": "conflict_skip",
                        "reason": "field conflict with existing customer",
                        "conflict_type": "field_conflict", "conflicts": conflicts,
                        "existing_customer_id": phone_match_ids[0]}
            return {"decision": "update_missing_only",
                    "reason": "single phone match, fill blanks",
                    "conflict_type": None, "existing_customer_id": phone_match_ids[0]}
        return {"decision": "conflict_multi_phone",
                "reason": "%d customers share this phone" % n,
                "conflict_type": "multi_phone", "conflicts": list(phone_match_ids)}

    if name_match_id:
        return {"decision": "conflict_name_only",
                "reason": "name-only match is unsafe", "conflict_type": "name_only",
                "existing_customer_id": name_match_id}

    return {"decision": "insert_with_warning",
            "reason": "no phone, no name match", "conflict_type": None}


CSV_COLUMNS = ("legacy_customer_id", "customer_name", "caller_phone_raw", "area",
               "service_state", "marketing_source", "first_contact_date",
               "last_known_equipment", "notes")
REQUIRED_COLUMNS = ("legacy_customer_id", "customer_name")


def parse_csv_text(text):
    """Parse CSV text into a list of dicts with all CSV_COLUMNS present (missing -> '').
    Header keys are stripped + lowercased. Raises ValueError if a required column is absent."""
    reader = csv.DictReader(io.StringIO(text))
    header = [(h or "").strip().lower() for h in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise ValueError("CSV missing required column(s): %s" % ", ".join(missing))
    rows = []
    for raw in reader:
        norm = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        rows.append({c: norm.get(c, "") for c in CSV_COLUMNS})
    return rows


def read_csv_rows(path):
    """Read a CSV file (utf-8-sig tolerant) and return parsed rows."""
    from pathlib import Path
    return parse_csv_text(Path(path).read_text(encoding="utf-8-sig"))


# ---------------------------------------------------------------------------
# Orchestration (I/O) — exercised by scripts/verify_customer_migration.py
# ---------------------------------------------------------------------------

CONFLICT_DECISIONS = ("conflict_skip", "conflict_multi_phone", "conflict_name_only")
OUTPUT_DIR = "migration_output"  # gitignored — holds customer phones/names


def _make_call(client):
    """Return a call(method, args) helper for Frappe whitelisted methods (REST)."""
    def call(method, args=None):
        return client._request("POST", "/api/method/%s" % method,
                               payload=(args or {}))["message"]
    return call


def resolve_safe_group_territory(client):
    """Find a non-group Customer Group + Territory (group nodes are invalid parents)."""
    groups = client.list_docs("Customer Group", filters=[["is_group", "=", 0]],
                              fields=["name"], limit=1)
    territories = client.list_docs("Territory", filters=[["is_group", "=", 0]],
                                   fields=["name"], limit=1)
    if not groups:
        raise RuntimeError("No non-group Customer Group found.")
    if not territories:
        raise RuntimeError("No non-group Territory found.")
    return groups[0]["name"], territories[0]["name"]


def lookup_for_row(client, call, write_fields):
    """Gather the lookup results classify_row needs. Returns a dict of kwargs."""
    legacy_id = write_fields["legacy_customer_id"]
    phone = write_fields["normalized_phone"]
    name = write_fields["customer_name"]

    legacy_exists = False
    if legacy_id:
        legacy_exists = bool(client.find_one(
            "Customer", filters=[["legacy_customer_id", "=", legacy_id]]))

    phone_match_ids = call("baro_crm.api.customer_migration.find_customers_by_phone",
                           {"phone": phone}) if phone else []

    existing_customer = None
    if len(phone_match_ids) == 1:
        doc = client.get_doc("Customer", phone_match_ids[0])
        existing_customer = {f: (doc.get(f) or "") for f in COMPARE_FIELDS}

    name_match_id = None
    if not phone and name:
        m = client.find_one("Customer", filters=[["customer_name", "=", name]])
        name_match_id = m["name"] if m else None

    return {
        "phone_norm": phone, "legacy_exists": legacy_exists,
        "phone_match_ids": phone_match_ids, "existing_customer": existing_customer,
        "name_match_id": name_match_id,
    }


def _insert_customer(client, call, write_fields, group, territory, *, duplicate_warning):
    doc = {
        "doctype": "Customer", "customer_type": "Company",
        "customer_group": group, "territory": territory,
        "customer_name": write_fields["customer_name"] or write_fields["normalized_phone"],
        "normalized_phone": write_fields["normalized_phone"],
        "legacy_customer_id": write_fields["legacy_customer_id"],
        "source_system": write_fields["source_system"],
        "import_batch_id": write_fields["import_batch_id"],
        "city_area": write_fields["city_area"],
        "service_state": write_fields["service_state"] or None,
        "first_seen": write_fields["first_seen"] or None,
        "last_known_equipment": write_fields["last_known_equipment"],
        "duplicate_warning": 1 if duplicate_warning else 0,
    }
    created = client.create_doc("Customer", doc)
    return created.get("name")


def _fill_blanks(client, customer_id, write_fields):
    """Update only the fields that are currently blank on the existing Customer."""
    existing = client.get_doc("Customer", customer_id)
    patch = {}
    fillable = ("normalized_phone", "legacy_customer_id", "source_system",
                "import_batch_id", "city_area", "service_state",
                "first_seen", "last_known_equipment")
    for f in fillable:
        if not (existing.get(f) or "") and write_fields.get(f):
            patch[f] = write_fields[f]
    if patch:
        client.update_doc("Customer", customer_id, patch)
    return list(patch.keys())


def _post_comment(call, customer_id, row):
    """Fold marketing_source + notes into a Customer Comment (no dedicated field)."""
    bits = []
    if row.get("source_system"):
        bits.append("source=%s" % row["source_system"])
    if row.get("marketing_source"):
        bits.append("marketing=%s" % row["marketing_source"])
    if row.get("notes"):
        bits.append(row["notes"])
    if not bits:
        return
    call("frappe.client.insert", {"doc": {
        "doctype": "Comment", "comment_type": "Comment",
        "reference_doctype": "Customer", "reference_name": customer_id,
        "content": "Migration import: " + " | ".join(bits),
    }})


def run_migration(client, rows, *, source_system, batch_id, execute,
                  chunk_size=500, error_budget=0.05):
    """Classify + (optionally) write each row. Returns a summary dict and writes
    plan_<batch>.csv and conflicts_<batch>.csv under migration_output/."""
    import os
    call = _make_call(client)
    group = territory = None
    if execute:
        group, territory = resolve_safe_group_territory(client)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    plan_path = os.path.join(OUTPUT_DIR, "plan_%s.csv" % batch_id)
    conflict_path = os.path.join(OUTPUT_DIR, "conflicts_%s.csv" % batch_id)

    summary = {d: 0 for d in (
        "skip_already_imported", "insert_new", "update_missing_only",
        "conflict_skip", "conflict_multi_phone", "conflict_name_only",
        "insert_with_warning")}
    summary["written"] = 0
    summary["failures"] = 0
    summary["batch_id"] = batch_id

    plan_f = open(plan_path, "w", newline="", encoding="utf-8")
    conflict_f = open(conflict_path, "w", newline="", encoding="utf-8")
    plan_w = csv.writer(plan_f)
    conflict_w = csv.writer(conflict_f)
    plan_w.writerow(["legacy_customer_id", "customer_name", "normalized_phone",
                     "decision", "reason", "customer_id", "error"])
    conflict_w.writerow(["legacy_customer_id", "source_system", "conflict_type",
                         "csv_customer_name", "existing_customer_id",
                         "detail", "recommended_action"])

    chunk_total = 0
    chunk_fail = 0
    try:
        for i, row in enumerate(rows):
            wf = build_write_fields(row, source_system=source_system, batch_id=batch_id)
            lk = lookup_for_row(client, call, wf)
            decision = classify_row(wf, **lk)
            d = decision["decision"]
            summary[d] += 1
            customer_id = decision.get("existing_customer_id") or ""
            error = ""

            if execute and d in ("insert_new", "insert_with_warning",
                                 "update_missing_only"):
                chunk_total += 1
                try:
                    if d == "update_missing_only":
                        _fill_blanks(client, customer_id, wf)
                    else:
                        customer_id = _insert_customer(
                            client, call, wf, group, territory,
                            duplicate_warning=(d == "insert_with_warning"))
                        if wf["normalized_phone"]:
                            call("baro_crm.api.customer_migration.ensure_customer_contact",
                                 {"customer_id": customer_id,
                                  "phone": wf["normalized_phone"],
                                  "first_name": wf["customer_name"] or None})
                    _post_comment(call, customer_id, {**row, "source_system": source_system})
                    summary["written"] += 1
                except Exception as exc:  # REST 4xx/5xx or validation error
                    error = str(exc)
                    chunk_fail += 1
                    summary["failures"] += 1

            if d in CONFLICT_DECISIONS:
                conflict_w.writerow([
                    wf["legacy_customer_id"], source_system, decision["conflict_type"],
                    wf["customer_name"], customer_id,
                    repr(decision.get("conflicts", decision.get("reason"))),
                    "Dispatcher review",
                ])

            plan_w.writerow([wf["legacy_customer_id"], wf["customer_name"],
                             wf["normalized_phone"], d, decision["reason"],
                             customer_id, error])

            if execute and chunk_total and chunk_total % chunk_size == 0:
                rate = chunk_fail / chunk_total
                if rate > error_budget:
                    raise RuntimeError(
                        "Aborting: failure rate %.1f%% exceeds budget %.0f%% after %d writes."
                        % (rate * 100, error_budget * 100, chunk_total))
    finally:
        plan_f.close()
        conflict_f.close()

    summary["plan_csv"] = plan_path
    summary["conflict_csv"] = conflict_path
    return summary


def main():
    import argparse
    import sys
    import uuid
    from datetime import date
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Existing Customer Migration (K)")
    parser.add_argument("--input", required=True, help="CSV file path")
    parser.add_argument("--source-system", required=True, dest="source_system")
    parser.add_argument("--batch-id", dest="batch_id", default=None)
    parser.add_argument("--execute", action="store_true",
                        help="Actually write. Without it, dry-run only (default).")
    parser.add_argument("--chunk-size", type=int, default=500, dest="chunk_size")
    parser.add_argument("--error-budget", type=float, default=0.05, dest="error_budget")
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from erpnext_client import get_client  # lazy: keeps module import network-free

    batch_id = args.batch_id or ("%s-%s-%s" % (
        args.source_system, date.today().strftime("%Y%m%d"), uuid.uuid4().hex[:6]))

    rows = read_csv_rows(args.input)
    print("Loaded %d rows from %s" % (len(rows), args.input))
    print("Batch: %s   Mode: %s" % (batch_id, "EXECUTE" if args.execute else "DRY-RUN"))

    client = get_client()
    if args.execute and client.config.dry_run:
        print("Refusing --execute while ERPNEXT_DRY_RUN is truthy. Set ERPNEXT_DRY_RUN=0.")
        sys.exit(1)

    summary = run_migration(
        client, rows, source_system=args.source_system, batch_id=batch_id,
        execute=args.execute, chunk_size=args.chunk_size, error_budget=args.error_budget)

    print("\n=== Summary ===")
    for k in ("skip_already_imported", "insert_new", "insert_with_warning",
              "update_missing_only", "conflict_skip", "conflict_multi_phone",
              "conflict_name_only", "written", "failures"):
        print("  %-22s %d" % (k, summary[k]))
    print("  plan     -> %s" % summary["plan_csv"])
    print("  conflicts-> %s" % summary["conflict_csv"])
    if summary["failures"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
