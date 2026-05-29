# Existing Customer Migration (K) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import 5–6k scattered existing customers into ERPNext as normalized, dedup-safe `Customer` + `Contact` records so the F drawer recognizes returning callers.

**Architecture:** A Python CLI (`scripts/migrate_customers.py`) owns the match/decision logic as pure, unit-tested functions and talks to ERPNext through the existing `src/erpnext_client.py` REST client. Three thin whitelisted server methods (`baro_crm/baro_crm/api/customer_migration.py`) re-expose F's phone-dedup + contact helpers and add a two-step rollback. Nine `Customer` custom fields ship via the existing fixture. Default mode is dry-run; `--execute` writes; rollback is keyed on `import_batch_id`.

**Tech Stack:** Python 3 stdlib (`csv`, `argparse`, `unittest`), Frappe v15 whitelisted methods, ERPNext REST, the project's `verify_*.py` smoke-script convention.

**Source spec:** `docs/superpowers/specs/2026-05-25-customer-migration-design.md` (approved 2026-05-29).

---

## Plan-phase decisions (resolving spec ambiguities — read before starting)

These were settled during writing-plans self-review. They override the spec where noted.

1. **`legacy_customer_id` is indexed but NOT `unique`.** The spec section 5 marks it unique. A unique Data field would collide on the empty string `''` that every *non-migrated* Customer carries, blocking normal Customer creation. Idempotency is enforced instead by the script's step-1 lookup. (Task 1.)
2. **`marketing_source` has no custom field** (spec section 5 lists none). It is folded into the migration Comment alongside `notes` and `source_system`. (Task 8 / run_migration.)
3. **Phone normalization is reimplemented locally** as `normalize_phone_local` with F's exact algorithm, rather than a per-row REST round-trip. 6k rows × one network call each to normalize would be slow and untestable offline. Unit tests pin it to F's documented examples. (Task 2.)
4. **Three thin wrappers, not two.** The spec promised two; `ensure_customer_contact` is added as a third because replicating Contact's `phone_nos` + Dynamic Link child-table shaping over REST is error-prone — reusing F's helper is DRY and safer. The spec section 12 explicitly left wrapper placement to the plan phase. (Task 5.)
5. **Conflict comparison fields** are `customer_name, city_area, service_state, last_known_equipment, first_seen`. A differing name on a phone match is a real "is this the same person?" signal, so `customer_name` is included. (Task 3.)

---

## File Structure

- `baro_crm/baro_crm/fixtures/custom_field.json` — **modify**: append 1 section break + 9 `Customer` custom fields.
- `baro_crm/baro_crm/hooks.py` — **modify**: add a second Custom Field fixtures filter for `dt = Customer`.
- `scripts/migrate_customers.py` — **create**: pure decision logic + CLI orchestration. Pure functions importable without `.env`/network.
- `tests/test_migrate_customers.py` — **create**: stdlib `unittest` for the pure functions (no server).
- `baro_crm/baro_crm/api/customer_migration.py` — **create**: 3 whitelisted methods (`find_customers_by_phone`, `ensure_customer_contact`, `rollback_batch`).
- `docs/templates/customers_import_v1.csv` — **create**: header + 2 example rows.
- `scripts/verify_customer_migration.py` — **create**: live smoke (dry-run → execute → rollback), mirrors `verify_create_repair_job.py`.
- `baro_crm/baro_crm/api/repair_job.py` — **modify**: `search_link` returns `duplicate_warning` for Customer (amber-dot source).
- `baro_crm/baro_crm/public/js/cockpit.js` — **modify**: amber dot in customer typeahead.
- `docs/superpowers/specs/2026-05-25-customer-migration-design.md` + `docs/superpowers/specs/2026-05-19-baro-crm-roadmap.md` — **modify**: status → Shipped at close-out.

**Deploy** (same as prior phases): `scp -r "Erpnext Baro\baro_crm" admin1@100.127.172.110:/home/admin1/` then `ssh ... "cd ~/baro_crm && ./install.sh"` (runs `bench migrate` → fires fixtures + `after_migrate`). The Python CLI runs locally from the project root against the live site via `.env` REST creds.

---

# PHASE A — Schema (Customer custom fields + fixtures filter)

### Task 1: Append 9 Customer custom fields to the fixture

**Files:**
- Modify: `baro_crm/baro_crm/fixtures/custom_field.json`

- [ ] **Step 1: Append the section break + 9 fields**

The file is currently a JSON array of 3 Repair Job custom fields ending at line 42 (`]` on line 43). Insert the following 10 objects *before* the closing `]`, adding a comma after the existing last object (`Repair Job-address_needs_review`).

```json
 ,
 {
  "doctype": "Custom Field",
  "name": "Customer-baro_crm_section",
  "dt": "Customer",
  "fieldname": "baro_crm_section",
  "label": "Baro CRM",
  "fieldtype": "Section Break",
  "insert_after": "customer_name",
  "collapsible": 1,
  "module": "Baro CRM"
 },
 {
  "doctype": "Custom Field",
  "name": "Customer-normalized_phone",
  "dt": "Customer",
  "fieldname": "normalized_phone",
  "label": "Normalized Phone",
  "fieldtype": "Data",
  "insert_after": "baro_crm_section",
  "search_index": 1,
  "unique": 0,
  "description": "Phone dedup target (+<digits>). Set by customer migration (K). Not unique — many customers have no phone.",
  "module": "Baro CRM"
 },
 {
  "doctype": "Custom Field",
  "name": "Customer-legacy_customer_id",
  "dt": "Customer",
  "fieldname": "legacy_customer_id",
  "label": "Legacy Customer ID",
  "fieldtype": "Data",
  "insert_after": "normalized_phone",
  "search_index": 1,
  "unique": 0,
  "description": "Source system's own ID. Migration idempotency key. NOT unique (empty-string collision on non-migrated customers).",
  "module": "Baro CRM"
 },
 {
  "doctype": "Custom Field",
  "name": "Customer-source_system",
  "dt": "Customer",
  "fieldname": "source_system",
  "label": "Source System",
  "fieldtype": "Data",
  "insert_after": "legacy_customer_id",
  "description": "Per-source label recorded at import time.",
  "module": "Baro CRM"
 },
 {
  "doctype": "Custom Field",
  "name": "Customer-import_batch_id",
  "dt": "Customer",
  "fieldname": "import_batch_id",
  "label": "Import Batch ID",
  "fieldtype": "Data",
  "insert_after": "source_system",
  "search_index": 1,
  "description": "Re-run / rollback handle for the customer migration.",
  "module": "Baro CRM"
 },
 {
  "doctype": "Custom Field",
  "name": "Customer-duplicate_warning",
  "dt": "Customer",
  "fieldname": "duplicate_warning",
  "label": "Possible Duplicate",
  "fieldtype": "Check",
  "insert_after": "import_batch_id",
  "default": "0",
  "description": "Set to 1 when imported without a phone/name match. F drawer shows an amber dot.",
  "module": "Baro CRM"
 },
 {
  "doctype": "Custom Field",
  "name": "Customer-city_area",
  "dt": "Customer",
  "fieldname": "city_area",
  "label": "City / Area",
  "fieldtype": "Data",
  "insert_after": "duplicate_warning",
  "description": "City / neighborhood from the source 'area' column.",
  "module": "Baro CRM"
 },
 {
  "doctype": "Custom Field",
  "name": "Customer-service_state",
  "dt": "Customer",
  "fieldname": "service_state",
  "label": "Service State",
  "fieldtype": "Select",
  "options": "\nTexas\nFlorida\nNew York\nNew Jersey",
  "insert_after": "city_area",
  "search_index": 1,
  "description": "US state (TX/FL/NY/NJ). Explicit from source or inferred from area.",
  "module": "Baro CRM"
 },
 {
  "doctype": "Custom Field",
  "name": "Customer-first_seen",
  "dt": "Customer",
  "fieldname": "first_seen",
  "label": "First Seen",
  "fieldtype": "Date",
  "insert_after": "service_state",
  "description": "First-contact date from the source data.",
  "module": "Baro CRM"
 },
 {
  "doctype": "Custom Field",
  "name": "Customer-last_known_equipment",
  "dt": "Customer",
  "fieldname": "last_known_equipment",
  "label": "Last Known Equipment",
  "fieldtype": "Data",
  "insert_after": "first_seen",
  "description": "Free-text equipment note from the source. Future sub-project promotes this to a DocType.",
  "module": "Baro CRM"
 }
```

- [ ] **Step 2: Validate JSON parses**

Run: `python -c "import json; json.load(open(r'baro_crm/baro_crm/fixtures/custom_field.json', encoding='utf-8')); print('ok', len(json.load(open(r'baro_crm/baro_crm/fixtures/custom_field.json', encoding='utf-8'))), 'fields')"`
Expected: `ok 13 fields`

- [ ] **Step 3: Commit**

```bash
git add baro_crm/baro_crm/fixtures/custom_field.json
git commit -m "feat(K): add 9 Customer custom fields for migration (normalized_phone, legacy id, batch, etc.)"
```

### Task 2: Extend the hooks.py fixtures filter to export the Customer fields

**Files:**
- Modify: `baro_crm/baro_crm/hooks.py:24-40`

- [ ] **Step 1: Add a second Custom Field filter entry**

In `hooks.py`, the `fixtures` list has a Custom Field entry filtered to `dt = "Repair Job"` and a Role entry. Add a new Custom Field dict **between** them (a separate fixture entry is required — one filter can't span two `dt` values):

```python
fixtures = [
    {
        "dt": "Custom Field",
        "filters": [
            ["dt", "=", "Repair Job"],
            ["fieldname", "in", [
                "service_state",
                "service_address_text",
                "address_needs_review",
            ]],
        ],
    },
    {
        "dt": "Custom Field",
        "filters": [
            ["dt", "=", "Customer"],
            ["fieldname", "in", [
                "baro_crm_section",
                "normalized_phone",
                "legacy_customer_id",
                "source_system",
                "import_batch_id",
                "duplicate_warning",
                "city_area",
                "service_state",
                "first_seen",
                "last_known_equipment",
            ]],
        ],
    },
    {
        "dt": "Role",
        "filters": [["name", "in", ["Baro Dispatcher", "Baro Reader"]]],
    },
]
```

- [ ] **Step 2: Validate the module imports**

Run: `python -c "import ast; ast.parse(open(r'baro_crm/baro_crm/hooks.py', encoding='utf-8').read()); print('hooks.py parses')"`
Expected: `hooks.py parses`

- [ ] **Step 3: Commit**

```bash
git add baro_crm/baro_crm/hooks.py
git commit -m "feat(K): export Customer migration custom fields via fixtures"
```

### ★ CHECKPOINT — Task 3: User deploys Phase A + verifies the columns exist

**This is a user-side checkpoint. Pause and hand off.**

- [ ] **Step 1: Deploy**

```
scp -r "Erpnext Baro\baro_crm" admin1@100.127.172.110:/home/admin1/
ssh admin1@100.127.172.110 "cd ~/baro_crm && ./install.sh"
```

- [ ] **Step 2: Confirm the columns landed**

```
ssh admin1@100.127.172.110 "docker compose -f ~/frappe_docker/pwd.yml exec -T backend bench --site frontend execute frappe.client.get_list --kwargs \"{'doctype':'Custom Field','filters':{'dt':'Customer'},'fields':['fieldname'],'limit_page_length':20}\""
```
Expected: 10 rows including `normalized_phone`, `legacy_customer_id`, `import_batch_id`, `duplicate_warning`, `service_state`.

Green = proceed to Phase B.

---

# PHASE B — Pure decision logic + unit tests (TDD, no server)

### Task 4: Create migrate_customers.py with pure helpers + first failing test

**Files:**
- Create: `scripts/migrate_customers.py`
- Create: `tests/test_migrate_customers.py`

- [ ] **Step 1: Write the failing test for phone normalization + state inference**

Create `tests/test_migrate_customers.py`:

```python
"""Unit tests for the pure logic in scripts/migrate_customers.py.
No network, no .env. Run: python tests/test_migrate_customers.py -v
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import migrate_customers as mc  # noqa: E402


class TestNormalizePhone(unittest.TestCase):
    def test_us_10_digit(self):
        self.assertEqual(mc.normalize_phone_local("212-555-0101"), "+12125550101")

    def test_formatted_with_plus(self):
        self.assertEqual(mc.normalize_phone_local("+1 (212) 555-0101"), "+12125550101")

    def test_uk(self):
        self.assertEqual(mc.normalize_phone_local("+44 20 7946 0958"), "+442079460958")

    def test_empty(self):
        self.assertEqual(mc.normalize_phone_local(""), "")
        self.assertEqual(mc.normalize_phone_local(None), "")

    def test_garbage_no_digits(self):
        self.assertEqual(mc.normalize_phone_local("call me"), "")


class TestInferServiceState(unittest.TestCase):
    def test_explicit_abbrev(self):
        self.assertEqual(mc.infer_service_state("", "TX"), "Texas")

    def test_explicit_full_name_wins(self):
        self.assertEqual(mc.infer_service_state("Miami", "New York"), "New York")

    def test_infer_from_area_city(self):
        self.assertEqual(mc.infer_service_state("Brooklyn", ""), "New York")

    def test_infer_from_bare_code_token(self):
        self.assertEqual(mc.infer_service_state("Austin, TX", ""), "Texas")

    def test_no_match_returns_empty(self):
        self.assertEqual(mc.infer_service_state("Springfield", ""), "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to confirm it fails (module not found yet)**

Run: `python tests/test_migrate_customers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'migrate_customers'`.

- [ ] **Step 3: Create scripts/migrate_customers.py with the two pure functions**

Create `scripts/migrate_customers.py`:

```python
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
```

- [ ] **Step 4: Run the tests — they pass**

Run: `python tests/test_migrate_customers.py -v`
Expected: PASS (10 tests in the two classes).

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_customers.py tests/test_migrate_customers.py
git commit -m "feat(K): pure phone-normalize + state-inference helpers with unit tests"
```

### Task 5: Add build_write_fields + conflict detection (TDD)

**Files:**
- Modify: `scripts/migrate_customers.py`
- Modify: `tests/test_migrate_customers.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_migrate_customers.py` before the `if __name__` guard:

```python
class TestBuildWriteFields(unittest.TestCase):
    def test_resolves_phone_and_state(self):
        row = {
            "legacy_customer_id": "L1", "customer_name": "Sunrise Diner",
            "caller_phone_raw": "212-555-0101", "area": "Brooklyn",
            "service_state": "", "first_contact_date": "2023-04-01",
            "last_known_equipment": "Combi Oven",
        }
        w = mc.build_write_fields(row, source_system="legacy", batch_id="b1")
        self.assertEqual(w["normalized_phone"], "+12125550101")
        self.assertEqual(w["service_state"], "New York")
        self.assertEqual(w["customer_name"], "Sunrise Diner")
        self.assertEqual(w["city_area"], "Brooklyn")
        self.assertEqual(w["legacy_customer_id"], "L1")
        self.assertEqual(w["source_system"], "legacy")
        self.assertEqual(w["import_batch_id"], "b1")
        self.assertEqual(w["first_seen"], "2023-04-01")
        self.assertEqual(w["last_known_equipment"], "Combi Oven")


class TestValuesConflict(unittest.TestCase):
    def test_both_empty_no_conflict(self):
        self.assertFalse(mc.values_conflict("", ""))

    def test_fill_blank_is_not_conflict(self):
        self.assertFalse(mc.values_conflict("Miami", ""))
        self.assertFalse(mc.values_conflict("", "Miami"))

    def test_case_insensitive_equal_no_conflict(self):
        self.assertFalse(mc.values_conflict(" miami ", "Miami"))

    def test_differ_is_conflict(self):
        self.assertTrue(mc.values_conflict("Miami", "Orlando"))


class TestDetectFieldConflicts(unittest.TestCase):
    def test_name_conflict_surfaces(self):
        w = {"customer_name": "Joe Pizza", "city_area": "Miami",
             "service_state": "Florida", "last_known_equipment": "", "first_seen": ""}
        existing = {"customer_name": "Joes Pizzeria", "city_area": "Miami",
                    "service_state": "Florida", "last_known_equipment": "", "first_seen": ""}
        conflicts = mc.detect_field_conflicts(w, existing)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["field"], "customer_name")

    def test_no_conflict_when_existing_blank(self):
        w = {"customer_name": "Joe Pizza", "city_area": "Miami",
             "service_state": "Florida", "last_known_equipment": "Fryer", "first_seen": ""}
        existing = {"customer_name": "Joe Pizza", "city_area": "",
                    "service_state": "", "last_known_equipment": "", "first_seen": ""}
        self.assertEqual(mc.detect_field_conflicts(w, existing), [])
```

- [ ] **Step 2: Run — confirm failures**

Run: `python tests/test_migrate_customers.py -v`
Expected: FAIL — `AttributeError: module 'migrate_customers' has no attribute 'build_write_fields'`.

- [ ] **Step 3: Implement the three functions**

Append to `scripts/migrate_customers.py` (after `infer_service_state`):

```python
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
```

- [ ] **Step 4: Run — pass**

Run: `python tests/test_migrate_customers.py -v`
Expected: PASS (all classes).

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_customers.py tests/test_migrate_customers.py
git commit -m "feat(K): build_write_fields + field-conflict detection with unit tests"
```

### Task 6: Add classify_row decision engine (TDD)

**Files:**
- Modify: `scripts/migrate_customers.py`
- Modify: `tests/test_migrate_customers.py`

- [ ] **Step 1: Write the failing tests covering all 7 decisions**

Append to `tests/test_migrate_customers.py` before the guard:

```python
class TestClassifyRow(unittest.TestCase):
    BASE = {"customer_name": "X", "city_area": "Miami", "service_state": "Florida",
            "last_known_equipment": "", "first_seen": ""}

    def test_skip_already_imported(self):
        r = mc.classify_row(self.BASE, phone_norm="+12125550101",
                            legacy_exists=True, phone_match_ids=[], existing_customer=None,
                            name_match_id=None)
        self.assertEqual(r["decision"], "skip_already_imported")

    def test_insert_new_when_phone_no_match(self):
        r = mc.classify_row(self.BASE, phone_norm="+12125550101",
                            legacy_exists=False, phone_match_ids=[], existing_customer=None,
                            name_match_id=None)
        self.assertEqual(r["decision"], "insert_new")

    def test_update_missing_only_on_clean_single_match(self):
        existing = {"customer_name": "X", "city_area": "", "service_state": "",
                    "last_known_equipment": "", "first_seen": ""}
        r = mc.classify_row(self.BASE, phone_norm="+12125550101",
                            legacy_exists=False, phone_match_ids=["CUST-1"],
                            existing_customer=existing, name_match_id=None)
        self.assertEqual(r["decision"], "update_missing_only")
        self.assertEqual(r["existing_customer_id"], "CUST-1")

    def test_conflict_skip_on_field_conflict(self):
        existing = {"customer_name": "Different Co", "city_area": "Orlando",
                    "service_state": "Florida", "last_known_equipment": "", "first_seen": ""}
        r = mc.classify_row(self.BASE, phone_norm="+12125550101",
                            legacy_exists=False, phone_match_ids=["CUST-1"],
                            existing_customer=existing, name_match_id=None)
        self.assertEqual(r["decision"], "conflict_skip")
        self.assertEqual(r["conflict_type"], "field_conflict")
        self.assertTrue(r["conflicts"])

    def test_conflict_multi_phone(self):
        r = mc.classify_row(self.BASE, phone_norm="+12125550101",
                            legacy_exists=False, phone_match_ids=["CUST-1", "CUST-2"],
                            existing_customer=None, name_match_id=None)
        self.assertEqual(r["decision"], "conflict_multi_phone")
        self.assertEqual(r["conflict_type"], "multi_phone")

    def test_conflict_name_only_when_no_phone(self):
        r = mc.classify_row(self.BASE, phone_norm="",
                            legacy_exists=False, phone_match_ids=[], existing_customer=None,
                            name_match_id="CUST-9")
        self.assertEqual(r["decision"], "conflict_name_only")
        self.assertEqual(r["existing_customer_id"], "CUST-9")

    def test_insert_with_warning_when_no_phone_no_name(self):
        r = mc.classify_row(self.BASE, phone_norm="",
                            legacy_exists=False, phone_match_ids=[], existing_customer=None,
                            name_match_id=None)
        self.assertEqual(r["decision"], "insert_with_warning")
```

- [ ] **Step 2: Run — confirm failures**

Run: `python tests/test_migrate_customers.py -v`
Expected: FAIL — `AttributeError: ... 'classify_row'`.

- [ ] **Step 3: Implement classify_row**

Append to `scripts/migrate_customers.py`:

```python
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
```

- [ ] **Step 4: Run — pass**

Run: `python tests/test_migrate_customers.py -v`
Expected: PASS (all 7 classify cases + earlier classes).

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_customers.py tests/test_migrate_customers.py
git commit -m "feat(K): classify_row decision engine (7 decisions) with unit tests"
```

### Task 7: Add CSV parsing (TDD)

**Files:**
- Modify: `scripts/migrate_customers.py`
- Modify: `tests/test_migrate_customers.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_migrate_customers.py` before the guard:

```python
class TestParseCsvText(unittest.TestCase):
    HEADER = ("legacy_customer_id,customer_name,caller_phone_raw,area,service_state,"
              "marketing_source,first_contact_date,last_known_equipment,notes")

    def test_parses_full_row(self):
        text = self.HEADER + "\nL1,Sunrise Diner,212-555-0101,Brooklyn,,Google,2023-01-01,Oven,vip\n"
        rows = mc.parse_csv_text(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["customer_name"], "Sunrise Diner")
        self.assertEqual(rows[0]["area"], "Brooklyn")
        self.assertEqual(rows[0]["notes"], "vip")

    def test_missing_optional_columns_default_blank(self):
        text = "legacy_customer_id,customer_name\nL2,Joe\n"
        rows = mc.parse_csv_text(text)
        self.assertEqual(rows[0]["caller_phone_raw"], "")
        self.assertEqual(rows[0]["area"], "")

    def test_header_whitespace_and_case_normalized(self):
        text = " Legacy_Customer_ID , Customer_Name \nL3,Ann\n"
        rows = mc.parse_csv_text(text)
        self.assertEqual(rows[0]["legacy_customer_id"], "L3")
        self.assertEqual(rows[0]["customer_name"], "Ann")

    def test_missing_required_column_raises(self):
        with self.assertRaises(ValueError):
            mc.parse_csv_text("customer_name\nJoe\n")
```

- [ ] **Step 2: Run — confirm failures**

Run: `python tests/test_migrate_customers.py -v`
Expected: FAIL — `AttributeError: ... 'parse_csv_text'`.

- [ ] **Step 3: Implement parse_csv_text + read_csv_rows**

Add `import csv` and `import io` to the top imports of `scripts/migrate_customers.py` (next to `import re`), then append:

```python
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
```

- [ ] **Step 4: Run — pass**

Run: `python tests/test_migrate_customers.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_customers.py tests/test_migrate_customers.py
git commit -m "feat(K): CSV parsing with header normalization + required-column check"
```

---

# PHASE C — Server wrappers

### Task 8: Create customer_migration.py whitelisted methods

**Files:**
- Create: `baro_crm/baro_crm/api/customer_migration.py`

- [ ] **Step 1: Write the module**

Create `baro_crm/baro_crm/api/customer_migration.py`:

```python
"""Customer migration (K) — thin server-side wrappers.

These re-expose F's existing dedup/contact helpers to the local migration CLI
and add a two-step rollback. No business decisions live here — the CLI owns
the match/decide logic. Keep this module thin.
"""
import hashlib

import frappe
from frappe import _


@frappe.whitelist()
def find_customers_by_phone(phone):
    """Sorted list of Customer IDs reachable from a phone (any format).
    Re-exposes baro_crm.api.repair_job._find_customers_by_phone."""
    if not frappe.has_permission("Customer", "read"):
        frappe.throw(_("Not permitted to read Customer"), frappe.PermissionError)
    from baro_crm.api.repair_job import normalize_phone, _find_customers_by_phone
    return sorted(_find_customers_by_phone(normalize_phone(phone)))


@frappe.whitelist()
def ensure_customer_contact(customer_id, phone, first_name=None):
    """Idempotently ensure the Customer has a Contact carrying this phone.
    Re-exposes baro_crm.api.repair_job._ensure_customer_contact."""
    if not frappe.has_permission("Contact", "create"):
        frappe.throw(_("Not permitted to create Contact"), frappe.PermissionError)
    from baro_crm.api.repair_job import normalize_phone, _ensure_customer_contact
    return _ensure_customer_contact(customer_id, normalize_phone(phone), first_name=first_name)


def _rollback_token(batch_id):
    site = getattr(frappe.local, "site", "") or ""
    return hashlib.sha256(("%s:%s:baro-rollback" % (batch_id, site)).encode()).hexdigest()[:12]


@frappe.whitelist()
def rollback_batch(batch_id, confirm_token=None):
    """Two-step rollback of an import batch. First call (no token) returns a count
    + confirm_token. Second call with the matching token deletes. Customers with
    linked Repair Jobs are skipped. Intended to run via `bench execute` (Administrator)."""
    roles = frappe.get_roles()
    if not (frappe.has_permission("Customer", "delete") or "System Manager" in roles):
        frappe.throw(_("Not permitted to roll back a migration batch"), frappe.PermissionError)
    if not batch_id:
        frappe.throw(_("batch_id is required"))

    names = frappe.get_all("Customer", filters={"import_batch_id": batch_id}, pluck="name")
    token = _rollback_token(batch_id)

    if confirm_token != token:
        return {
            "ok": False, "requires_confirmation": True, "batch_id": batch_id,
            "customer_count": len(names), "confirm_token": token,
            "message": ("%d customers in batch '%s'. Re-run with confirm_token to delete."
                        % (len(names), batch_id)),
        }

    deleted, skipped = [], []
    for name in names:
        rj_count = frappe.db.count("Repair Job", {"customer": name})
        if rj_count:
            skipped.append({"customer": name, "repair_jobs": rj_count})
            continue
        contacts = frappe.db.sql_list("""
            SELECT DISTINCT parent FROM `tabDynamic Link`
            WHERE link_doctype = 'Customer' AND link_name = %s AND parenttype = 'Contact'
        """, (name,))
        for c in contacts:
            frappe.delete_doc("Contact", c, ignore_permissions=True, force=True)
        frappe.delete_doc("Customer", name, ignore_permissions=True, force=True)
        deleted.append(name)

    frappe.db.commit()
    return {
        "ok": True, "batch_id": batch_id,
        "deleted": deleted, "deleted_count": len(deleted),
        "skipped": skipped, "skipped_count": len(skipped),
    }
```

- [ ] **Step 2: Validate it parses**

Run: `python -c "import ast; ast.parse(open(r'baro_crm/baro_crm/api/customer_migration.py', encoding='utf-8').read()); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add baro_crm/baro_crm/api/customer_migration.py
git commit -m "feat(K): thin server wrappers — find_customers_by_phone, ensure_customer_contact, rollback_batch"
```

---

# PHASE D — CLI orchestration

### Task 9: Wire the migration run loop + plan/conflict CSV output

**Files:**
- Modify: `scripts/migrate_customers.py`

- [ ] **Step 1: Append the orchestration + main()**

Append to `scripts/migrate_customers.py`. This is the only part that touches the network; `erpnext_client` is imported lazily inside `main()`.

```python
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
```

- [ ] **Step 2: Confirm pure tests still pass + module imports clean (no network)**

Run: `python tests/test_migrate_customers.py -v`
Expected: PASS — adding orchestration didn't break pure logic, and `import migrate_customers` still works without `.env`.

- [ ] **Step 3: Confirm CLI arg parsing works without touching the network**

Run: `python scripts/migrate_customers.py --help`
Expected: argparse usage text listing `--input`, `--source-system`, `--execute`, `--chunk-size`, `--error-budget`. (No `.env`/network needed — `get_client` is imported lazily after arg parsing.)

- [ ] **Step 4: Commit**

```bash
git add scripts/migrate_customers.py
git commit -m "feat(K): migration run loop, REST writes, plan/conflict CSV output, CLI"
```

### Task 10: Add the sample CSV template

**Files:**
- Create: `docs/templates/customers_import_v1.csv`

- [ ] **Step 1: Write the template (header + 2 example rows)**

Create `docs/templates/customers_import_v1.csv`:

```csv
legacy_customer_id,customer_name,caller_phone_raw,area,service_state,marketing_source,first_contact_date,last_known_equipment,notes
EXAMPLE-001,Sunrise Diner,(212) 555-0101,Brooklyn,,Google,2023-04-12,Combi Oven,Net-30 account
EXAMPLE-002,Bayfront Cafe,305-555-0199,Miami FL,Florida,Referral,2022-11-03,Walk-in Cooler,Prefers morning calls
```

- [ ] **Step 2: Confirm the parser accepts the template**

Run: `python -c "import sys; sys.path.insert(0,'scripts'); import migrate_customers as mc; rows=mc.read_csv_rows('docs/templates/customers_import_v1.csv'); print(len(rows),'rows', rows[0]['customer_name'])"`
Expected: `2 rows Sunrise Diner`

- [ ] **Step 3: Commit**

```bash
git add docs/templates/customers_import_v1.csv
git commit -m "docs(K): sample customer import CSV template (v1 locked schema)"
```

---

# PHASE E — Live smoke + checkpoint

### Task 11: Create verify_customer_migration.py

**Files:**
- Create: `scripts/verify_customer_migration.py`

- [ ] **Step 1: Write the smoke script**

Create `scripts/verify_customer_migration.py`. It builds a tiny in-memory CSV with a unique per-run prefix, runs dry-run then execute, asserts the F dedup helper now finds the imported phone, then rolls the batch back via the two-step token, and finally sweeps any leftovers.

```python
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
```

- [ ] **Step 2: Confirm it parses + dry-run path is reachable offline**

Run: `python -c "import ast; ast.parse(open(r'scripts/verify_customer_migration.py', encoding='utf-8').read()); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_customer_migration.py
git commit -m "test(K): live smoke — dry-run, execute, dedup recognition, idempotent re-run, rollback"
```

### ★ CHECKPOINT — Task 12: User runs the live smoke

**User-side checkpoint. Pause and hand off.** Run from the project root (Phase A must already be deployed so the Customer fields exist).

- [ ] **Step 1: Dry-run smoke (safe, no writes)**

```
python scripts/verify_customer_migration.py
```
Expected: `OK dry-run classifies, writes nothing` then the dry-run-only notice.

- [ ] **Step 2: Full smoke (writes + rolls back its own data)**

```
$env:ERPNEXT_DRY_RUN = "0"
python scripts/verify_customer_migration.py --execute
```
Expected: all 5 checks `OK`, ending `All K smoke checks passed.`

- [ ] **Step 3: (Optional) Dry-run against the real sample template**

```
python scripts/migrate_customers.py --input docs/templates/customers_import_v1.csv --source-system sample
```
Expected: summary with `insert_new 2`, `written 0`, and a `migration_output/plan_*.csv` written (and gitignored).

Green = proceed to Phase F.

---

# PHASE F — Amber-dot drawer polish + close-out

### Task 13: search_link returns duplicate_warning for Customer

**Files:**
- Modify: `baro_crm/baro_crm/api/repair_job.py:1089-1096`

- [ ] **Step 1: Include duplicate_warning in the Customer query + result**

Replace the `frappe.get_list(...)` call and the return line in `search_link` (currently lines 1089–1096) with:

```python
    want_warn = doctype == "Customer" and frappe.db.has_column("Customer", "duplicate_warning")
    fields = ["name", title_field] + (["duplicate_warning"] if want_warn else [])

    rows = frappe.get_list(
        doctype,
        fields=fields,
        or_filters=[["name", "like", q], [title_field, "like", q]] if query else None,
        order_by="modified desc",
        limit_page_length=limit,
    )
    out = []
    for r in rows:
        item = {"value": r["name"], "label": r.get(title_field) or r["name"]}
        if want_warn and r.get("duplicate_warning"):
            item["warn"] = 1
        out.append(item)
    return out
```

- [ ] **Step 2: Validate it parses**

Run: `python -c "import ast; ast.parse(open(r'baro_crm/baro_crm/api/repair_job.py', encoding='utf-8').read()); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add baro_crm/baro_crm/api/repair_job.py
git commit -m "feat(K): search_link surfaces duplicate_warning for Customer typeahead"
```

### Task 14: Amber dot in the customer typeahead

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js:2414-2419`

- [ ] **Step 1: Render the dot when a result is flagged**

Replace the `items` map (currently lines 2414–2419 in `doCustomerTypeahead`) with:

```javascript
    const d = state.createDraft || {};
    const items = (results || []).slice(0, 8).map(r => `
      <button type="button" class="typeahead-item" role="option"
              data-customer-id="${escapeHtml(r.value)}"
              data-customer-name="${escapeHtml(r.label || r.value)}">
        ${r.warn ? '<span class="dup-dot" title="Possible duplicate — review"></span>' : ''}${escapeHtml(r.label || r.value)}
      </button>`).join('');
```

(The existing `const d = state.createDraft || {};` line just below the old map block — at line 2413 — is now duplicated; delete the later standalone one so `d` is declared once.)

- [ ] **Step 2: Add the dot style**

Add to `baro_crm/baro_crm/public/css/cockpit.css` (near the other `.typeahead-item` rules):

```css
.baro-cockpit .typeahead-item .dup-dot {
  display: inline-block;
  width: 8px; height: 8px;
  margin-right: 8px;
  border-radius: 50%;
  background: #f59e0b; /* amber */
  vertical-align: middle;
}
```

- [ ] **Step 3: Commit**

```bash
git add baro_crm/baro_crm/public/js/cockpit.js baro_crm/baro_crm/public/css/cockpit.css
git commit -m "feat(K): amber dot on possible-duplicate customers in drawer typeahead"
```

### ★ CHECKPOINT — Task 15: User deploys F-phase + browser-verifies the amber dot

**User-side checkpoint.**

- [ ] **Step 1: Deploy** (`scp` + `./install.sh` as in Task 3).
- [ ] **Step 2:** Open `/repair-jobs`, click Create, type a name that matches a Customer imported with `duplicate_warning=1` (e.g. a no-phone row from a real batch). Confirm an amber dot shows left of that suggestion and not on clean customers.

Green = proceed to close-out.

### Task 16: Close-out — mark spec + roadmap Shipped, tag

**Files:**
- Modify: `docs/superpowers/specs/2026-05-25-customer-migration-design.md:4`
- Modify: `docs/superpowers/specs/2026-05-19-baro-crm-roadmap.md` (K entry)

- [ ] **Step 1: Update the spec status**

In `docs/superpowers/specs/2026-05-25-customer-migration-design.md`, change line 4 from `Status: Pending user review.` to:

```
Status: Shipped 2026-05-29. Tag: customer-migration-shipped.
```

- [ ] **Step 2: Mark K shipped in the roadmap**

In `docs/superpowers/specs/2026-05-19-baro-crm-roadmap.md`, find the K sub-project line and mark it Shipped (match the format used for F/J/G, e.g. append ` — Shipped 2026-05-29`).

- [ ] **Step 3: Verify the full unit suite once more**

Run: `python tests/test_migrate_customers.py -v`
Expected: PASS (all classes).

- [ ] **Step 4: Commit + tag**

```bash
git add docs/superpowers/specs/2026-05-25-customer-migration-design.md docs/superpowers/specs/2026-05-19-baro-crm-roadmap.md
git commit -m "docs(K): mark Existing Customer Migration shipped"
git tag customer-migration-shipped
```

---

## Self-Review (writing-plans checklist — completed)

**1. Spec coverage:** goal → all tasks; CSV schema (§2) → Task 7 + Task 10; architecture (§3) → Tasks 8–9; match/decision (§4) → Task 6; 9 custom fields (§5) → Task 1; dry-run/execute + error budget + idempotent (§6) → Task 9 + smoke Task 11; F benefit + amber dot (§7) → Tasks 13–14; safety/auth incl. migration_output gitignore (§8) → already committed `e441ee2`, dir created in `run_migration`; rollback two-step + RJ-link skip (§9) → Task 8 + smoke Task 11; acceptance criteria (§11) → smoke Task 12 covers dry-run plan/conflict, execute, dedup recognition, idempotent re-run, rollback. **No gaps.**

**2. Placeholder scan:** none — every code step is complete; commands have expected output.

**3. Type/name consistency:** decision strings, `COMPARE_FIELDS`, `build_write_fields`/`classify_row`/`detect_field_conflicts`/`values_conflict`/`parse_csv_text`/`run_migration`/`_make_call` signatures are identical across script, tests, and smoke. Wrapper method paths (`baro_crm.api.customer_migration.*`) match between Task 8 and the callers in Tasks 9/11.

**Spec deviations** (documented in "Plan-phase decisions" above): legacy_customer_id not unique; marketing_source → Comment; local phone normalize; 3 wrappers not 2.
