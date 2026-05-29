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

import re

# ---------------------------------------------------------------------------
# Pure logic (no I/O) — unit-tested
# ---------------------------------------------------------------------------

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
        el = e.casefold()
        for canon, kws in STATE_KEYWORDS:
            if el == canon.casefold() or el in kws:
                return canon
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
            conflicts = detect_field_conflicts(write_fields, existing_customer or {})
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
