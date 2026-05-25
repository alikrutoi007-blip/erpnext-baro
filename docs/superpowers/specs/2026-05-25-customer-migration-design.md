# Existing Customer Migration (K) — design

Date: 2026-05-25
Status: Pending user review.
Roadmap parent: `2026-05-19-baro-crm-roadmap.md` (sub-project K)
Implementation target: `scripts/migrate_customers.py` + `baro_crm` Custom Fields fixture extension
Estimated effort: 2–3 days

---

## 1. Goal

Import the existing 5–6k customers scattered across multiple sources into ERPNext as `Customer` + `Contact` records, normalized and dedup-safe, so the F drawer recognizes returning callers instead of treating them as first-timers.

**Non-goals (deferred):**
- Auto-fuzzy-merge of similar names. Suggestions only. (Belongs to H.)
- Importing historical Repair Jobs. (Belongs to a separate sub-project later.)
- Importing Customer Equipment as its own DocType. (Stored as a Customer custom field for now.)
- Address records. The F drawer creates them per-RJ when a real street is typed.

---

## 2. Source data

Multiple CSVs, one per source system. Filename pattern: `{source_system}_{batch_id}.csv` (e.g. `legacy_sheet_2024_b001.csv`).

### Locked CSV schema (v1)

| Column | Required | Notes |
|---|---|---|
| `legacy_customer_id` | yes | Source's own ID. Idempotency key for re-runs. |
| `customer_name` | yes | Free text. Used as Customer name + Contact first_name. |
| `caller_phone_raw` | recommended | Any format; script normalizes via F's `normalize_phone`. Empty allowed but row gets `MissingPhone` warning. |
| `area` | optional | City / neighborhood. Stored as `Customer.city_area`. |
| `service_state` | optional | TX / FL / NY / NJ. Inferred from `area` keyword match if blank. |
| `marketing_source` | optional | Free text. |
| `first_contact_date` | optional | ISO date; stored as Customer custom field `first_seen`. |
| `last_known_equipment` | optional | Free text. Stored as Customer custom field. |
| `notes` | optional | Written as a Customer Comment (not a field). |

Anything more is scope creep against the "returning-caller recognition" goal.

---

## 3. Architecture

K is a single Python CLI: `scripts/migrate_customers.py`.

```
CSV files ───►  migrate_customers.py
                  │
                  ├── reuses src/erpnext_client.py for REST
                  ├── reuses normalize_phone / _find_customers_by_phone via thin
                  │   whitelisted wrappers in baro_crm.api.customer_migration
                  └── outputs:
                        - plan_<batch_id>.csv  (every input row + decision + reason)
                        - conflicts_<batch_id>.csv  (rows needing dispatcher review)
```

No new Frappe app endpoints beyond two thin wrappers that re-expose F's existing helpers for the script's use.

---

## 4. Match + decision logic

Applied per CSV row, in order:

1. **Lookup by `legacy_customer_id`.** If a Customer already carries this id, **SKIP** (re-run safe). Log to plan CSV with `decision=skip_already_imported`.
2. **Lookup by normalized phone** via the F helper `_find_customers_by_phone`:
   - **0 matches** → `decision=insert_new`. Insert Customer + Contact.
   - **1 match** → check field conflicts. A "conflict" = CSV provides a non-empty value AND the existing Customer's corresponding field is non-empty AND the two values differ after case-insensitive whitespace-trimmed compare. Empty-vs-non-empty is not a conflict; that's a fill candidate.
     - No conflict → `decision=update_missing_only`. Fill blanks; do not overwrite populated fields.
     - Any conflict → `decision=conflict_skip`. Append to conflict CSV. Do not write.
   - **2+ matches** → `decision=conflict_multi_phone`. Append to conflict CSV. Do not write. This is the "phone shared across multiple customers" case the F drawer already blocks.
3. **No phone, name match** (exact, case-insensitive) → `decision=conflict_name_only`. Append to conflict CSV. Do not write. Reason: name-only matches are unsafe.
4. **No phone, no name match** → `decision=insert_with_warning`. Insert Customer with `duplicate_warning=1` so the F drawer flags it later for dispatcher review.

Conflict CSV columns:
`legacy_customer_id, source_system, conflict_type, csv_row_json, existing_customer_id, existing_value, csv_value, recommended_action`.

---

## 5. New Customer custom fields

Shipped via the existing `baro_crm/baro_crm/fixtures/custom_field.json` (extend, don't replace).

| Fieldname | Type | Indexed | Purpose |
|---|---|---|---|
| `normalized_phone` | Data | yes | F's phone dedup target. |
| `legacy_customer_id` | Data | yes (unique) | Idempotency key. |
| `source_system` | Data | no | Per-source label. |
| `import_batch_id` | Data | no | Re-run / rollback handle. |
| `duplicate_warning` | Check | no | F drawer amber dot. |
| `city_area` | Data | no | From CSV `area`. |
| `service_state` | Select (TX/FL/NY/NJ) | yes | Inferred or explicit. |
| `first_seen` | Date | no | First contact in source data. |
| `last_known_equipment` | Data | no | Free text from CSV. |

`hooks.py` fixtures filter extended to include `Customer` as a target DocType.

---

## 6. Dry-run vs Execute

- **Default mode is dry-run.** `--execute` required to write.
- **Conflicts are NEVER auto-resolved.** They land in the conflict CSV; dispatcher resolves manually (or via a future H tool).
- **Batched writes**, chunks of 500.
- **Error budget:** if any chunk has >5% failures, abort. A "failure" is any REST 4xx/5xx response or Frappe validation error during insert/update. Conflict-skips and missing-data warnings are NOT failures — they're expected output.
- **Idempotent re-run:** Re-running with the same CSV is safe — step 1 (`legacy_customer_id` lookup) skips already-imported rows.

CLI surface:
```
python scripts/migrate_customers.py \
  --input <dir-or-file>.csv \
  --source-system <label> \
  --batch-id <auto-or-supplied> \
  [--execute] \
  [--chunk-size 500] \
  [--error-budget 0.05]
```

---

## 7. How F benefits immediately

No F code change required (except the optional amber-dot polish below). Post-migration:
- F drawer's customer typeahead surfaces all imported names.
- `find_dedup_warnings` matches by `normalized_phone` against the new Customer field.
- A returning caller's phone hits the imported Customer → drawer shows the existing-customer banner.
- Customers with `duplicate_warning=1` get a visible amber dot in the typeahead (~10-line drawer add, included in K).

---

## 8. Safety + auth

- Migration runs against the live site through the existing REST credentials (`.env` `ERPNEXT_API_KEY` / `ERPNEXT_API_SECRET`). Reuses `erpnext_client.py`.
- Read paths permission-checked server-side automatically.
- Write paths require a user with Customer create perm. The Baro Dispatcher role already has it (J).
- Dry-run mode never writes; safe to share output CSVs with non-technical stakeholders for review.
- Conflict CSV may contain customer phone numbers and names. Do not commit it to git. Recommend a `migration_output/` directory in `.gitignore`.

---

## 9. Rollback

The `import_batch_id` field is the rollback handle. To undo a batch:
```bash
docker compose -f ~/frappe_docker/pwd.yml exec -T backend \
  bench --site frontend execute baro_crm.api.customer_migration.rollback_batch \
  --kwargs "{'batch_id': '...', 'confirm_token': '...'}"
```
The rollback whitelisted method:
- Counts the affected rows
- Returns the count + a confirm token
- Only deletes when re-called with the matching token (two-step like `rm -rf` confirmation)
- Deletes Customer + linked Contact in dependency order

Rollback is meant for "I imported the wrong file" not "I want to undo last week's batch after Repair Jobs were created against those Customers". If any imported Customer has a linked Repair Job, rollback skips it and reports.

---

## 10. Out of scope / explicitly NOT in K

- Fuzzy-matching algorithm (Levenshtein, Soundex, etc.). Only exact normalized-phone and exact case-insensitive name. H will add fuzzy.
- Multi-phone-per-customer support. K imports one phone per Customer row. If a real customer has 3 phones in your source data spread across 3 rows, K creates 3 Customer records and the conflict report flags them. H reconciles.
- Customer Equipment as a DocType. Stored as `last_known_equipment` string on Customer. A future sub-project creates the DocType + migrates the string.
- Historical Repair Job migration. K is customer-only.
- Address creation from `area` text. Too ambiguous. F drawer creates Addresses per-RJ when a real street is typed.

---

## 11. Acceptance criteria

- Dry-run against a 200-row sample CSV produces a plan CSV with every row classified and a conflict CSV with the expected matches surfaced.
- Execute against the same sample creates 200 Customers + Contacts in ERPNext.
- F drawer's typeahead surfaces those Customers within seconds.
- F drawer's `find_dedup_warnings` flags a phone match for a known imported phone.
- Re-running the same CSV in execute mode produces 0 new writes.
- Rollback by `batch_id` removes all 200 cleanly when no RJs are linked.

---

## 12. Open questions for plan phase

None blocking. Surface during writing-plans if any:
- Whether the two helper whitelisted methods (`customer_migration.find_customers_by_phone`, `customer_migration.rollback_batch`) belong in a new `baro_crm/baro_crm/api/customer_migration.py` module or extend `repair_job.py`. Recommend new module to keep `repair_job.py` from becoming a junk drawer.
- Sample CSV template — ship at `docs/templates/customers_import_v1.csv` so dispatchers can format their data against a known schema.
