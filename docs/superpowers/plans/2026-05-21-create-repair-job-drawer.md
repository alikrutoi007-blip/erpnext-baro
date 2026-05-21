# Create Repair Job drawer — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the cockpit's "+ New Repair Job" button (which currently jumps to `/app/repair-job/new`) with a right-side in-cockpit drawer that creates a Repair Job via a minimal field set, runs non-blocking dedup checks (phone / name / active-job), and opens the inspector for the new RJ on success. Fold in the audit polish (status-popover regression fix, focus trap helper, `extractError`, `kanbanCardHtml`/`renderRow` extraction, `state.jobsById`, kanban natural-height with sticky heads, paginated `get_jobs`).

**Architecture:** Backend-first (helpers → resolvers → endpoints → fixtures → smoke), then cockpit refactors that the drawer depends on, then scale-handling CSS, then the drawer itself, then sign-off. Server is source of truth — no optimistic insert. Drawer mutually exclusive with inspector. Phone multi-match blocks silent creation until dispatcher picks one or explicitly checks "Create new anyway". Contact creation never blocks RJ creation; on Contact failure the RJ is created with `contact=None` plus a `contact-create-failed` warning.

**Tech Stack:** Frappe v15 (Python/Jinja), vanilla JS (cockpit.js ~1670 lines after E), SortableJS 1.15.6 (already vendored), existing `erpnext_client.py` for smoke tests. Deploy: scp + `install.sh` over Tailscale.

**Source spec:** `docs/superpowers/specs/2026-05-21-create-repair-job-drawer-design.md` (approved 2026-05-21, commit `79d2371`). Sub-project F in the 8-project roadmap.

---

## Phases and checkpoints

5 phases. **At each checkpoint the implementer pauses and the user runs the smoke + a focused browser check before continuing.**

| Phase | Tasks | Deliverable | Checkpoint |
|---|---|---|---|
| A. Backend foundation | T1–T8 | All Python helpers + endpoints + fixtures + smoke + seeder | T9 — user runs `install.sh` + `verify_create_repair_job.py --execute` |
| B. Cockpit refactors + audit polish | T10–T16 | Bug 1.1 fixed, focus trap helper, `extractError` decoded, render helpers extracted, `jobsById` map, misc polish | T17 — user verifies status pill click works + nothing regressed |
| C. Scale handling | T18–T19 | Kanban natural-height + sticky heads + "Load 500 more" button | T20 — user verifies scrolling with synthetic seed |
| D. Drawer | T21–T30 | Full drawer with typeahead, dedup banners, multi-match block, surgical insert, dirty-confirm | T31 — user runs 20 manual browser tests + smoke |
| E. Sign-off | T32 | Spec/roadmap flipped to Shipped, tag pushed | none |

---

## Phase A — Backend foundation

### Task 1: Pure helpers — defaults, normalize_phone, parse_address, find_customers, ensure_contact

**Files:**
- Modify: `baro_crm/baro_crm/api/repair_job.py`

- [ ] **Step 1: Add the safe-defaults helpers near the top of the file (after the existing `STATES` constant)**

```python
def _get_default_customer_group():
    """Non-group Customer Group. Prefer 'Commercial'. Throws if no non-group exists."""
    if (frappe.db.exists('Customer Group', 'Commercial')
            and not frappe.db.get_value('Customer Group', 'Commercial', 'is_group')):
        return 'Commercial'
    rows = frappe.db.sql_list("""
        SELECT name FROM `tabCustomer Group`
        WHERE is_group = 0 ORDER BY lft LIMIT 1
    """)
    if not rows:
        frappe.throw(_('No non-group Customer Group exists. Create one in Setup → Customer Group.'))
    return rows[0]


def _get_default_territory():
    if (frappe.db.exists('Territory', 'Commercial')
            and not frappe.db.get_value('Territory', 'Commercial', 'is_group')):
        return 'Commercial'
    rows = frappe.db.sql_list("""
        SELECT name FROM `tabTerritory`
        WHERE is_group = 0 ORDER BY lft LIMIT 1
    """)
    if not rows:
        frappe.throw(_('No non-group Territory exists.'))
    return rows[0]
```

- [ ] **Step 2: Replace the existing `normalize_phone` (if any) with the strict version**

Search the file for `def normalize_phone` and replace its body with:

```python
def normalize_phone(raw):
    """Always returns +<digits> or ''. Never returns the raw string."""
    if not raw:
        return ''
    import re
    digits = re.sub(r'\D', '', str(raw))
    if not digits:
        return ''
    if len(digits) == 10:
        return '+1' + digits
    if len(digits) == 11 and digits.startswith('1'):
        return '+' + digits
    return '+' + digits
```

If `normalize_phone` doesn't exist yet, append this definition after `_get_default_territory`.

- [ ] **Step 3: Add the address parser**

Append immediately after `normalize_phone`:

```python
def _parse_address_text(raw):
    """Conservative. 'Complete' only when street# + city + state are all parsed."""
    import re
    m = re.match(
        r'^(?P<street>\d+\s+[^,]+),\s*(?P<city>[^,]+),\s*(?P<state>[A-Z]{2})\s*(?P<zip>\d{5})?',
        raw.strip(), re.IGNORECASE,
    )
    if not m:
        return {'complete': False}
    return {
        'complete': True,
        'street': m.group('street').strip(),
        'city': m.group('city').strip(),
        'state': m.group('state').upper(),
        'zip': m.group('zip'),
    }
```

- [ ] **Step 4: Add the phone→customers fan-out helper**

Append after `_parse_address_text`:

```python
def _find_customers_by_phone(phone_norm):
    """Set of distinct Customer IDs reachable from this phone.
    Sources: Contact.mobile_no, Contact.phone, Repair Job.caller_phone,
    Customer.normalized_phone (when sub-project K's migration adds the column).
    """
    if not phone_norm:
        return set()
    cust_ids = set()

    # (1) Contact.mobile_no / Contact.phone → Dynamic Link → Customer
    contacts = frappe.db.sql_list("""
        SELECT DISTINCT name FROM `tabContact`
        WHERE mobile_no = %s OR phone = %s
    """, (phone_norm, phone_norm))
    if contacts:
        placeholders = ', '.join(['%s'] * len(contacts))
        linked = frappe.db.sql_list(f"""
            SELECT DISTINCT link_name FROM `tabDynamic Link`
            WHERE link_doctype = 'Customer'
              AND parent IN ({placeholders})
        """, contacts)
        cust_ids.update(linked)

    # (2) Existing Repair Job caller_phone → its Customer
    rj_customers = frappe.db.sql_list("""
        SELECT DISTINCT customer FROM `tabRepair Job`
        WHERE caller_phone = %s AND customer IS NOT NULL AND customer != ''
    """, (phone_norm,))
    cust_ids.update(rj_customers)

    # (3) Future K: Customer.normalized_phone. Frappe v15: has_column(doctype, fieldname),
    # doctype name (no "tab" prefix). Returns False for unknown cols (no raise).
    if frappe.db.has_column('Customer', 'normalized_phone'):
        cust_ids.update(frappe.db.sql_list("""
            SELECT name FROM `tabCustomer` WHERE normalized_phone = %s
        """, (phone_norm,)))

    return cust_ids
```

- [ ] **Step 5: Add the contact-ensure helper (idempotent)**

Append after `_find_customers_by_phone`:

```python
def _ensure_customer_contact(customer_id, phone_norm, first_name=None):
    """Idempotent. Ensures the Customer has a Contact carrying this phone.
    Strengthens future phone-based dedup. Returns the Contact name."""
    if not customer_id or not phone_norm:
        return None
    existing = frappe.db.sql_list("""
        SELECT DISTINCT c.name FROM `tabContact` c
        JOIN `tabDynamic Link` dl ON dl.parent = c.name
        WHERE dl.link_doctype = 'Customer' AND dl.link_name = %s
          AND (c.mobile_no = %s OR c.phone = %s)
        LIMIT 1
    """, (customer_id, phone_norm, phone_norm))
    if existing:
        return existing[0]

    contact = frappe.get_doc({
        'doctype': 'Contact',
        'first_name': first_name or 'Primary',
        'mobile_no': phone_norm,
        'phone_nos': [{
            'phone': phone_norm,
            'is_primary_phone': 1,
            'is_primary_mobile_no': 1,
        }],
        'links': [{'link_doctype': 'Customer', 'link_name': customer_id}],
    }).insert(ignore_permissions=False)
    return contact.name
```

- [ ] **Step 6: Commit**

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
git add baro_crm/baro_crm/api/repair_job.py
git -c user.name="Baro Service" -c user.email="baroservicellc@gmail.com" `
  commit -m "feat(api): F helpers — safe defaults, normalize_phone, parse_address, find_customers_by_phone, ensure_customer_contact"
```

---

### Task 2: `_resolve_customer` — strict priority, no silent fuzzy

**Files:**
- Modify: `baro_crm/baro_crm/api/repair_job.py`

- [ ] **Step 1: Append `_resolve_customer` to the file (after `_ensure_customer_contact`)**

```python
def _resolve_customer(payload, warnings):
    """Strict priority — no silent fuzzy-link. See spec §8.2."""
    # 1. Explicit typeahead pick
    if payload.get('customer_id'):
        cid = payload['customer_id']
        if not frappe.db.exists('Customer', cid):
            frappe.throw(_("Selected Customer '{0}' no longer exists").format(cid))
        return cid

    phone_norm = normalize_phone(payload.get('caller_phone'))
    typed_name = (payload.get('customer_name') or '').strip()
    typed_name_norm = typed_name.lower()
    force_create = bool(payload.get('force_create_new'))

    # 2. Phone match (exactly-one required)
    if phone_norm:
        matches = _find_customers_by_phone(phone_norm)
        if len(matches) == 1:
            cust = next(iter(matches))
            existing_name = (frappe.db.get_value('Customer', cust, 'customer_name') or '').strip().lower()
            if typed_name_norm and typed_name_norm != existing_name:
                warnings.append({
                    'kind': 'phone-vs-name',
                    'phone': phone_norm,
                    'customer': cust,
                    'message': f"Phone {phone_norm} belongs to existing Customer '{cust}'. Linked to that.",
                })
            return cust
        elif len(matches) > 1:
            if not force_create:
                frappe.throw(_(
                    "Phone {0} matches {1} customers. Pick one from the typeahead "
                    "or tick 'Create new anyway' to proceed with a new Customer."
                ).format(phone_norm, len(matches)), title=_('Ambiguous phone match'))
            warnings.append({
                'kind': 'phone-multi-match-overridden',
                'phone': phone_norm,
                'customers': sorted(matches),
                'message': f"Created new Customer despite {len(matches)} phone matches.",
            })
            # fall through to step 3/4

    # 3. Exact name match (case-insensitive trim)
    if typed_name_norm:
        rows = frappe.db.sql_list("""
            SELECT name FROM `tabCustomer`
            WHERE LOWER(TRIM(customer_name)) = %s LIMIT 2
        """, (typed_name_norm,))
        if len(rows) == 1:
            return rows[0]
        if len(rows) > 1:
            frappe.throw(_("Multiple customers exactly match '{0}'. Pick one from the typeahead.").format(typed_name))

    # 4. Create new (typed name)
    if typed_name:
        cust = frappe.get_doc({
            'doctype': 'Customer',
            'customer_name': typed_name,
            'customer_type': 'Company',
            'customer_group': _get_default_customer_group(),
            'territory':      _get_default_territory(),
        }).insert(ignore_permissions=False)
        warnings.append({
            'kind': 'customer-created',
            'customer': cust.name,
            'message': f"Created new Customer '{typed_name}'.",
        })
        return cust.name

    # 5. Unknown caller fallback
    if phone_norm:
        cust = frappe.get_doc({
            'doctype': 'Customer',
            'customer_name': f'Unknown - {phone_norm}',
            'customer_type': 'Individual',
            'customer_group': _get_default_customer_group(),
            'territory':      _get_default_territory(),
        }).insert(ignore_permissions=False)
        warnings.append({
            'kind': 'unknown-caller',
            'message': f"No name given; created placeholder Customer 'Unknown - {phone_norm}'.",
        })
        return cust.name

    frappe.throw(_('Need either customer_name, customer_id, or caller_phone'))
```

- [ ] **Step 2: Commit**

```powershell
git add baro_crm/baro_crm/api/repair_job.py
git -c user.name="Baro Service" -c user.email="baroservicellc@gmail.com" `
  commit -m "feat(api): _resolve_customer with strict no-fuzzy priority"
```

---

### Task 3: `_resolve_address` — cautious

**Files:**
- Modify: `baro_crm/baro_crm/api/repair_job.py`

- [ ] **Step 1: Append `_resolve_address` (after `_resolve_customer`)**

```python
def _resolve_address(payload, customer_id, warnings):
    """Only create an Address doc when text parses into street + city + state
    (ZIP optional). Otherwise store raw text on the Repair Job + flag for review."""
    raw = (payload.get('service_address') or '').strip()
    if not raw:
        return None, None, 0

    parsed = _parse_address_text(raw)
    if parsed.get('complete'):
        addr = frappe.get_doc({
            'doctype': 'Address',
            'address_title': (payload.get('customer_name') or customer_id or 'Repair Job'),
            'address_type': 'Service',
            'address_line1': parsed['street'],
            'city': parsed['city'],
            'state': parsed.get('state'),
            'pincode': parsed.get('zip'),
            'country': 'United States',
            'links': [{'link_doctype': 'Customer', 'link_name': customer_id}] if customer_id else [],
        }).insert()
        return addr.name, raw, 0

    warnings.append({
        'kind': 'address-incomplete',
        'message': "Address looks incomplete — stored as raw text on the job. Review and create a proper Address later.",
    })
    return None, raw, 1
```

- [ ] **Step 2: Commit**

```powershell
git add baro_crm/baro_crm/api/repair_job.py
git -c user.name="Baro Service" -c user.email="baroservicellc@gmail.com" `
  commit -m "feat(api): _resolve_address with cautious Address creation"
```

---

### Task 4: `create_repair_job` — atomic insert with non-blocking Contact

**Files:**
- Modify: `baro_crm/baro_crm/api/repair_job.py`

This task implements the user's explicit requirement: `_ensure_customer_contact` runs inside a try/except. On failure, the warning kind `contact-create-failed` is appended and the RJ is still created with `contact=None`. Only Customer/RJ insert failures abort the whole flow.

- [ ] **Step 1: Append `create_repair_job` (after `_resolve_address`)**

```python
@frappe.whitelist()
def create_repair_job(payload):
    """Atomic create: resolves Customer + Contact (non-blocking) + Address + Repair Job.
    Contact creation never blocks RJ creation — on failure the RJ is created with
    contact=None and a 'contact-create-failed' warning is returned."""
    if not frappe.has_permission('Repair Job', 'create'):
        frappe.throw(_('Not permitted to create Repair Job'), frappe.PermissionError)

    import json as _json
    if isinstance(payload, str):
        payload = _json.loads(payload)

    warnings = []

    # Service state validation (defensive — UI should constrain)
    state = payload.get('service_state')
    if state not in ('Texas', 'Florida', 'New York', 'New Jersey'):
        frappe.throw(_("Service state must be one of Texas, Florida, New York, New Jersey"))

    # Required-field minimums (defensive)
    for required in ('equipment_type', 'symptom', 'urgency'):
        if not (payload.get(required) or '').strip():
            frappe.throw(_("{0} is required").format(required.replace('_', ' ').title()))

    phone_norm = normalize_phone(payload.get('caller_phone'))
    if not phone_norm and not payload.get('customer_name') and not payload.get('customer_id'):
        frappe.throw(_('Need either a customer or a caller phone'))

    # Customer (no silent fuzzy). Throws on multi-phone-match without force_create_new.
    customer_id = _resolve_customer(payload, warnings)

    # Contact — non-blocking. RJ is created even if Contact fails.
    # USER REQUIREMENT 2026-05-21: wrap in try/except, append 'contact-create-failed'
    # warning on failure, do NOT abort the whole flow.
    contact_id = None
    if phone_norm and customer_id:
        try:
            contact_id = _ensure_customer_contact(
                customer_id, phone_norm,
                first_name=(payload.get('contact_first_name') or None),
            )
        except Exception as e:
            warnings.append({
                'kind': 'contact-create-failed',
                'phone': phone_norm,
                'customer': customer_id,
                'message': (
                    f"Could not create or link Contact for phone {phone_norm}: {e}. "
                    "Repair Job created without contact."
                ),
            })
            contact_id = None
            # Log for diagnostics (writes to Error Log)
            frappe.log_error(
                title='F: contact-create-failed',
                message=frappe.get_traceback(),
            )

    # Address (cautious)
    address_id, address_text, needs_review = _resolve_address(payload, customer_id, warnings)

    # Repair Job
    doc = frappe.get_doc({
        'doctype': 'Repair Job',
        'naming_series': 'RJ-.YYYY.-',
        'status': 'New',
        'customer': customer_id,
        'contact': contact_id,
        'caller_phone': phone_norm,
        'business_phone_did': normalize_phone(payload.get('business_phone_did')),
        'area': (payload.get('area') or '').strip(),
        'service_state': state,
        'marketing_source': (payload.get('marketing_source') or '').strip(),
        'service_address': address_id,
        'service_address_text': address_text,
        'address_needs_review': needs_review,
        'equipment_type': payload['equipment_type'].strip(),
        'symptom': payload['symptom'].strip(),
        'urgency': payload['urgency'],
        'internal_comment': (payload.get('internal_comment') or '').strip() or None,
    })
    doc.insert()

    return {
        'ok': True,
        'name': doc.name,
        'doc': doc.as_dict(),
        'warnings': warnings,
    }
```

- [ ] **Step 2: Commit**

```powershell
git add baro_crm/baro_crm/api/repair_job.py
git -c user.name="Baro Service" -c user.email="baroservicellc@gmail.com" `
  commit -m "feat(api): create_repair_job with non-blocking Contact (contact-create-failed warning)"
```

---

### Task 5: `find_dedup_warnings` — non-blocking pre-check endpoint

**Files:**
- Modify: `baro_crm/baro_crm/api/repair_job.py`

- [ ] **Step 1: Append `find_dedup_warnings` (after `create_repair_job`)**

```python
@frappe.whitelist()
def find_dedup_warnings(customer=None, customer_name=None, caller_phone=None,
                       equipment_type=None, lookback_days=90):
    """Returns dedup hints WITHOUT blocking or linking. Drawer surfaces these
    as informational/blocking banners depending on kind. Mirrors the
    _resolve_customer checks but reports instead of throwing/creating."""
    out = {
        'phone_match_customer': None,
        'phone_multi_match': [],
        'name_match_customer': None,
        'similar_customers': [],
        'active_jobs': [],
    }
    if not frappe.has_permission('Repair Job', 'create'):
        return out

    phone_norm = normalize_phone(caller_phone)
    name_norm = (customer_name or '').strip().lower()

    # Phone
    if phone_norm:
        matches = _find_customers_by_phone(phone_norm)
        if len(matches) == 1:
            out['phone_match_customer'] = next(iter(matches))
        elif len(matches) > 1:
            out['phone_multi_match'] = sorted(matches)

    # Name — exact + prefix-similar
    if name_norm:
        rows = frappe.db.sql_list("""
            SELECT name FROM `tabCustomer`
            WHERE LOWER(TRIM(customer_name)) = %s LIMIT 2
        """, (name_norm,))
        if len(rows) == 1:
            out['name_match_customer'] = rows[0]
        if len(name_norm) >= 3:
            sim = frappe.db.sql("""
                SELECT name, customer_name FROM `tabCustomer`
                WHERE LOWER(TRIM(customer_name)) LIKE %s
                  AND LOWER(TRIM(customer_name)) != %s
                LIMIT 5
            """, (f'{name_norm}%', name_norm))
            out['similar_customers'] = [
                {'name': r[0], 'customer_name': r[1], 'why': 'starts with same prefix'}
                for r in sim
            ]

    # Active jobs (90-day window)
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=int(lookback_days))).isoformat()
    active_statuses = [
        'New', 'Need Follow-up', 'Diagnostics Offered', 'Waiting Prepayment',
        'Diagnostics Paid', 'Technician Assigned', 'Diagnostics In Progress',
        'Diagnosis Completed', 'Estimate Sent', 'Waiting Client Approval',
        'Parts Needed', 'Repair In Progress', 'Repair Completed', 'Invoice Sent',
    ]
    or_filters = []
    if customer:
        or_filters.append(['customer', '=', customer])
    if phone_norm:
        or_filters.append(['caller_phone', '=', phone_norm])
    if not or_filters:
        return out

    rjs = frappe.get_list('Repair Job',
        fields=['name', 'status', 'customer', 'caller_phone',
                'equipment_type', 'modified'],
        filters=[['status', 'in', active_statuses],
                 ['modified', '>=', cutoff]],
        or_filters=or_filters,
        limit_page_length=10,
        order_by='modified desc')

    for rj in rjs:
        reasons = []
        if customer and rj['customer'] == customer:
            reasons.append('same customer')
        if phone_norm and rj['caller_phone'] == phone_norm:
            reasons.append('same phone')
        if equipment_type and rj['equipment_type'] == equipment_type:
            reasons.append('same equipment')
        if reasons:
            rj['reason'] = ' + '.join(reasons)
            out['active_jobs'].append(rj)

    return out
```

- [ ] **Step 2: Commit**

```powershell
git add baro_crm/baro_crm/api/repair_job.py
git -c user.name="Baro Service" -c user.email="baroservicellc@gmail.com" `
  commit -m "feat(api): find_dedup_warnings non-blocking pre-check (90d lookback)"
```

---

### Task 6: Revised `get_jobs` — honest pagination

**Files:**
- Modify: `baro_crm/baro_crm/api/repair_job.py`

- [ ] **Step 1: Find the existing `get_jobs` and replace its body**

Search `repair_job.py` for `def get_jobs(`. Replace the entire function with:

```python
@frappe.whitelist()
def get_jobs(state=None, status=None, search=None,
             limit=500, offset=0, date_from=None):
    """Paginated list. Returns {jobs, offset, limit, total?, has_more}.
    `total` is None when search is active (frappe.db.count doesn't honor or_filters)."""
    limit = max(1, min(int(limit), 2000))
    offset = max(0, int(offset))

    filters = {}
    if state and state != 'All':
        filters['service_state'] = state
    if status:
        filters['status'] = status
    if date_from:
        filters['call_datetime'] = ['>=', date_from]

    or_filters = None
    if search:
        s = f'%{search}%'
        or_filters = [
            ['customer', 'like', s], ['caller_phone', 'like', s],
            ['area', 'like', s], ['equipment_type', 'like', s],
            ['equipment_brand', 'like', s], ['name', 'like', s],
        ]

    rows = frappe.get_list('Repair Job',
        fields=LIST_FIELDS + ['service_address_text', 'address_needs_review'],
        filters=filters, or_filters=or_filters,
        order_by='modified desc',
        limit_start=offset, limit_page_length=limit)

    result = {'jobs': rows, 'offset': offset, 'limit': limit}
    if or_filters:
        # frappe.db.count doesn't honor or_filters — return cheap proxy
        result['has_more'] = len(rows) == limit
        result['total'] = None
    else:
        total = frappe.db.count('Repair Job', filters=filters)
        result['total'] = total
        result['has_more'] = (offset + len(rows)) < total
    return result
```

- [ ] **Step 2: Commit**

```powershell
git add baro_crm/baro_crm/api/repair_job.py
git -c user.name="Baro Service" -c user.email="baroservicellc@gmail.com" `
  commit -m "feat(api): paginated get_jobs returning {jobs, total?, has_more}"
```

---

### Task 7: Custom Fields fixture + hooks.py extension

**Files:**
- Modify: `baro_crm/baro_crm/fixtures/custom_field.json`
- Modify: `baro_crm/baro_crm/hooks.py`

- [ ] **Step 1: Append two entries to `custom_field.json`**

Open `baro_crm/baro_crm/fixtures/custom_field.json`. The file is a JSON array of objects. Insert these two objects before the closing `]`:

```json
,
 {
  "doctype": "Custom Field",
  "name": "Repair Job-service_address_text",
  "dt": "Repair Job",
  "fieldname": "service_address_text",
  "label": "Service Address (raw text)",
  "fieldtype": "Small Text",
  "insert_after": "service_address",
  "description": "Raw text stored when the input couldn't be parsed into a clean Address doc. See address_needs_review.",
  "module": "Baro CRM"
 },
 {
  "doctype": "Custom Field",
  "name": "Repair Job-address_needs_review",
  "dt": "Repair Job",
  "fieldname": "address_needs_review",
  "label": "Address needs review",
  "fieldtype": "Check",
  "insert_after": "service_address_text",
  "default": "0",
  "description": "Set to 1 when service_address_text is populated but no Address doc was created.",
  "module": "Baro CRM"
 }
```

- [ ] **Step 2: Validate JSON**

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
python -c "import json; json.load(open('baro_crm/baro_crm/fixtures/custom_field.json'))"
```

Expected: no output (= valid JSON). If you get `json.decoder.JSONDecodeError`, fix the comma/bracket positions before continuing.

- [ ] **Step 3: Extend `hooks.py` fixtures filter**

Open `baro_crm/baro_crm/hooks.py`. Find the `fixtures = [...]` block. Replace it with:

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
    }
]
```

- [ ] **Step 4: Commit**

```powershell
git add baro_crm/baro_crm/fixtures/custom_field.json baro_crm/baro_crm/hooks.py
git -c user.name="Baro Service" -c user.email="baroservicellc@gmail.com" `
  commit -m "feat(fixtures): add service_address_text + address_needs_review Custom Fields"
```

---

### Task 8: Backend smoke script + synthetic seeder

**Files:**
- Create: `scripts/verify_create_repair_job.py`
- Create: `scripts/seed_synthetic_jobs.py`

Both scripts implement the user's explicit requirement: **unique generated test phone per run** + **`--clean-stale` flag** that sweeps `TEST-F-*` records older than 1 day.

- [ ] **Step 1: Create `verify_create_repair_job.py`**

Create `C:\Users\epmek\Documents\Erpnext Baro\scripts\verify_create_repair_job.py` with this exact content:

```python
#!/usr/bin/env python
"""F backend smoke. Calls create_repair_job + find_dedup_warnings against
the live ERPNext via the existing ERPNextClient. All test records get a
per-run TEST-F-* prefix on Customer names and are cleaned at the end.

Per the 2026-05-21 plan:
  - Unique generated test_phone per run (no fixed +12125559099)
  - --clean-stale sweeps TEST-F-* records older than 1 day before the run
    (default ON in --execute; disable with --no-clean-stale)
"""
import argparse, sys, uuid, random, time
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from erpnext_client import get_client, ERPNextError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true',
        help='Actually call create endpoints. Without this, only reads happen.')
    parser.add_argument('--keep', action='store_true', help='Skip post-run cleanup.')
    parser.add_argument('--clean-stale', dest='clean_stale', action='store_true', default=True,
        help='Before the run, delete TEST-F-* records older than 1 day. Default ON.')
    parser.add_argument('--no-clean-stale', dest='clean_stale', action='store_false',
        help='Skip the pre-run stale sweep.')
    parser.add_argument('--stale-hours', type=int, default=24,
        help='Hours threshold for stale TEST-F-* records (default 24).')
    args = parser.parse_args()

    client = get_client()
    if not args.execute and not client.config.dry_run:
        print('Refusing to run write tests without --execute or ERPNEXT_DRY_RUN=1.')
        sys.exit(1)

    # ---- Pre-run stale sweep ------------------------------------------------
    if args.clean_stale and args.execute:
        _clean_stale_test_records(client, hours=args.stale_hours)

    # ---- Per-run prefix + unique phone --------------------------------------
    run_id = f"TEST-F-{date.today().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
    # 4 random digits → 10-digit US number when prefixed with 212555. normalize_phone
    # takes 11 digits starting with 1, returns +<those 11 digits>.
    test_phone_suffix = ''.join(random.choices('0123456789', k=4))
    test_phone = '+1212555' + test_phone_suffix
    print(f"Run prefix : {run_id}")
    print(f"Test phone : {test_phone}\n")

    def call(method, args_=None):
        # Frappe REST whitelisted-method body: args at top level (NOT wrapped in {'args':...})
        return client._request('POST', f'/api/method/{method}',
                               payload=(args_ or {}))['message']

    failures = []
    rj_name = []

    def check(name, fn):
        try:
            fn()
            print(f"  OK   {name}")
        except Exception as e:
            failures.append((name, e))
            print(f"  FAIL {name}: {e}")

    # ---- T1: find_dedup_warnings shape -------------------------------------
    def t1():
        r = call('baro_crm.api.repair_job.find_dedup_warnings',
                 {'caller_phone': test_phone})
        assert isinstance(r, dict)
        for key in ('phone_match_customer', 'phone_multi_match',
                    'name_match_customer', 'similar_customers', 'active_jobs'):
            assert key in r, f"missing key {key}"
    check('find_dedup_warnings shape', t1)

    # ---- T2: create_repair_job minimal payload -----------------------------
    def t2():
        r = call('baro_crm.api.repair_job.create_repair_job', {'payload': {
            'customer_name': f"{run_id} Sunrise Diner",
            'caller_phone': test_phone,
            'service_state': 'New York',
            'equipment_type': 'Combi Oven',
            'symptom': 'Not heating',
            'urgency': 'Today',
        }})
        assert r['ok'] is True
        assert r['name'].startswith('RJ-')
        rj_name.append(r['name'])
    check('create_repair_job minimal payload', t2)

    # ---- T3: active-RJ warning surfaces -------------------------------------
    def t3():
        r = call('baro_crm.api.repair_job.find_dedup_warnings', {
            'caller_phone': test_phone,
            'equipment_type': 'Combi Oven',
        })
        assert any(j['name'] == rj_name[0] for j in r['active_jobs']), \
            f"expected RJ {rj_name[0]} in active_jobs, got {r['active_jobs']}"
    check('active-RJ warning fires', t3)

    # ---- T4: incomplete address → text + needs_review=1 --------------------
    def t4():
        unique4 = ''.join(random.choices('0123456789', k=4))
        r = call('baro_crm.api.repair_job.create_repair_job', {'payload': {
            'customer_name': f"{run_id} Vague Address Test",
            'caller_phone': '+1212556' + unique4,
            'service_state': 'New York',
            'equipment_type': 'Ice Machine',
            'symptom': 'Stopped making ice',
            'urgency': 'Scheduled',
            'service_address': 'Manhattan',   # incomplete
        }})
        assert r['doc']['service_address'] is None
        assert r['doc']['service_address_text'] == 'Manhattan'
        assert r['doc']['address_needs_review'] == 1
        rj_name.append(r['name'])
    check('incomplete address stored as text', t4)

    # ---- T5: bad customer_id rejected --------------------------------------
    def t5():
        try:
            call('baro_crm.api.repair_job.create_repair_job', {'payload': {
                'customer_id': 'NONEXISTENT-CUSTOMER-XYZ',
                'caller_phone': '+12125570001',
                'service_state': 'New York',
                'equipment_type': 'Fryer',
                'symptom': 'Test',
                'urgency': 'Scheduled',
            }})
            raise AssertionError('expected error for bad customer_id')
        except ERPNextError as e:
            assert 'no longer exists' in str(e) or 'does not exist' in str(e), \
                f"unexpected error: {e}"
    check('bad customer_id rejected', t5)

    # ---- T6: phone multi-match blocks; force_create_new bypasses -----------
    # Discover non-group Customer Group + Territory once
    groups = call('frappe.client.get_list', {
        'doctype': 'Customer Group',
        'filters': [['is_group', '=', 0]],
        'fields': ['name'], 'order_by': 'lft', 'limit_page_length': 1,
    })
    if not groups:
        raise AssertionError('No non-group Customer Group — cannot run T6 setup.')
    SAFE_GROUP = groups[0]['name']

    territories = call('frappe.client.get_list', {
        'doctype': 'Territory',
        'filters': [['is_group', '=', 0]],
        'fields': ['name'], 'order_by': 'lft', 'limit_page_length': 1,
    })
    if not territories:
        raise AssertionError('No non-group Territory — cannot run T6 setup.')
    SAFE_TERRITORY = territories[0]['name']

    def t6():
        # Use a different unique phone so T6 doesn't interact with T2/T3
        t6_suffix = ''.join(random.choices('0123456789', k=4))
        t6_phone = '+1212557' + t6_suffix

        cust1 = call('frappe.client.insert', {'doc': {
            'doctype': 'Customer',
            'customer_name': f"{run_id} MultiMatch A",
            'customer_type': 'Company',
            'customer_group': SAFE_GROUP,
            'territory': SAFE_TERRITORY,
        }})['name']
        cust2 = call('frappe.client.insert', {'doc': {
            'doctype': 'Customer',
            'customer_name': f"{run_id} MultiMatch B",
            'customer_type': 'Company',
            'customer_group': SAFE_GROUP,
            'territory': SAFE_TERRITORY,
        }})['name']
        rj1 = call('baro_crm.api.repair_job.create_repair_job', {'payload': {
            'customer_id': cust1, 'caller_phone': t6_phone,
            'service_state': 'New York', 'equipment_type': 'Probe',
            'symptom': 'setup A', 'urgency': 'Scheduled',
        }})['name']
        rj2 = call('baro_crm.api.repair_job.create_repair_job', {'payload': {
            'customer_id': cust2, 'caller_phone': t6_phone,
            'service_state': 'New York', 'equipment_type': 'Probe',
            'symptom': 'setup B', 'urgency': 'Scheduled',
        }})['name']
        rj_name.extend([rj1, rj2])

        # Without force_create_new → throw
        try:
            call('baro_crm.api.repair_job.create_repair_job', {'payload': {
                'customer_name': f"{run_id} MultiMatch Blocked",
                'caller_phone': t6_phone,
                'service_state': 'New York', 'equipment_type': 'Probe',
                'symptom': 'should be blocked', 'urgency': 'Scheduled',
            }})
            raise AssertionError('expected throw on multi-match without force_create_new')
        except ERPNextError as e:
            assert 'matches' in str(e).lower() or 'ambiguous' in str(e).lower(), \
                f"unexpected error text: {e}"

        # With force_create_new=true → succeeds, warning surfaces
        r = call('baro_crm.api.repair_job.create_repair_job', {'payload': {
            'customer_name': f"{run_id} MultiMatch Forced",
            'caller_phone': t6_phone,
            'force_create_new': True,
            'service_state': 'New York', 'equipment_type': 'Probe',
            'symptom': 'should succeed with force', 'urgency': 'Scheduled',
        }})
        assert r['ok'] is True
        assert any(w.get('kind') == 'phone-multi-match-overridden'
                   for w in r.get('warnings', [])), \
            f"expected phone-multi-match-overridden warning, got {r.get('warnings')}"
        rj_name.append(r['name'])
    check('phone multi-match blocks; force_create_new bypasses', t6)

    # ---- Cleanup -----------------------------------------------------------
    if not args.keep:
        print("\nCleaning up...")
        _cleanup_run(client, run_id, rj_name)

    # ---- Summary -----------------------------------------------------------
    if failures:
        print(f"\n{len(failures)} failure(s):")
        for name, e in failures:
            print(f"  - {name}: {e}")
        sys.exit(1)
    print("\nAll backend smoke checks passed.")


def _cleanup_run(client, run_id, rj_name):
    """Strict order: RJs → Contacts → Addresses → Customers."""
    for name in rj_name:
        try:
            client._request('DELETE', f'/api/resource/Repair Job/{name}')
            print(f"  deleted RJ {name}")
        except Exception as e:
            print(f"  cleanup warn: RJ {name}: {e}")

    test_customers = client.list_docs('Customer',
        filters=[['name', 'like', f'%{run_id}%']],
        fields=['name'], limit=50)

    for cust in test_customers:
        linked_contacts = client.list_docs('Contact',
            filters=[
                ['Dynamic Link', 'link_doctype', '=', 'Customer'],
                ['Dynamic Link', 'link_name', '=', cust['name']],
            ],
            fields=['name'], limit=20)
        for c in linked_contacts:
            try:
                client._request('DELETE', f'/api/resource/Contact/{c["name"]}')
                print(f"  deleted Contact {c['name']}")
            except Exception as e:
                print(f"  cleanup warn: Contact {c['name']}: {e}")

    for cust in test_customers:
        linked_addrs = client.list_docs('Address',
            filters=[
                ['Dynamic Link', 'link_doctype', '=', 'Customer'],
                ['Dynamic Link', 'link_name', '=', cust['name']],
            ],
            fields=['name'], limit=20)
        for a in linked_addrs:
            try:
                client._request('DELETE', f'/api/resource/Address/{a["name"]}')
                print(f"  deleted Address {a['name']}")
            except Exception as e:
                print(f"  cleanup warn: Address {a['name']}: {e}")

    for cust in test_customers:
        try:
            client._request('DELETE', f'/api/resource/Customer/{cust["name"]}')
            print(f"  deleted Customer {cust['name']}")
        except Exception as e:
            print(f"  cleanup warn: Customer {cust['name']}: {e}")


def _clean_stale_test_records(client, hours=24):
    """Pre-run sweep: delete TEST-F-* records older than `hours`."""
    print(f"Pre-run sweep: deleting TEST-F-* records older than {hours}h...")
    cutoff = (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
    stale_custs = client.list_docs('Customer',
        filters=[
            ['name', 'like', 'TEST-F-%'],
            ['creation', '<', cutoff],
        ],
        fields=['name'], limit=500)
    if not stale_custs:
        print("  (no stale TEST-F-* customers found)\n")
        return

    print(f"  {len(stale_custs)} stale TEST-F-* customers detected")
    for cust in stale_custs:
        # Delete linked RJs, Contacts, Addresses, then Customer
        rjs = client.list_docs('Repair Job',
            filters=[['customer', '=', cust['name']]],
            fields=['name'], limit=50)
        for rj in rjs:
            try: client._request('DELETE', f'/api/resource/Repair Job/{rj["name"]}')
            except Exception: pass
        for ent in ('Contact', 'Address'):
            ents = client.list_docs(ent,
                filters=[
                    ['Dynamic Link', 'link_doctype', '=', 'Customer'],
                    ['Dynamic Link', 'link_name', '=', cust['name']],
                ], fields=['name'], limit=20)
            for e in ents:
                try: client._request('DELETE', f'/api/resource/{ent}/{e["name"]}')
                except Exception: pass
        try: client._request('DELETE', f'/api/resource/Customer/{cust["name"]}')
        except Exception as e: print(f"  stale cleanup warn: Customer {cust['name']}: {e}")
    print(f"  swept {len(stale_custs)} stale Customer trees\n")


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Create `seed_synthetic_jobs.py`**

Create `C:\Users\epmek\Documents\Erpnext Baro\scripts\seed_synthetic_jobs.py`:

```python
#!/usr/bin/env python
"""Generate synthetic Repair Jobs for scale testing the cockpit's pagination
and kanban scroll. All seeded records carry a TEST-F-LOAD-<uuid> prefix on
their Customer names so they can be cleanly removed.

SAFETY: refuses to run unless BARO_ALLOW_SYNTHETIC=1 is set in the environment.
This prevents accidental seeding of real production sites.
"""
import argparse, os, sys, uuid, random
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from erpnext_client import get_client, ERPNextError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--count', type=int, default=100, help='Jobs to create')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--cleanup', action='store_true',
        help='Delete all TEST-F-LOAD-* records and exit')
    args = parser.parse_args()

    if os.environ.get('BARO_ALLOW_SYNTHETIC') != '1':
        print('Refusing to run. Set BARO_ALLOW_SYNTHETIC=1 in your env to enable.')
        sys.exit(2)

    client = get_client()
    if not args.execute:
        print('Use --execute to actually write.')
        sys.exit(1)

    def call(method, args_=None):
        return client._request('POST', f'/api/method/{method}',
                               payload=(args_ or {}))['message']

    if args.cleanup:
        _cleanup_all(client)
        return

    # Discover safe defaults
    groups = call('frappe.client.get_list', {
        'doctype': 'Customer Group',
        'filters': [['is_group', '=', 0]],
        'fields': ['name'], 'order_by': 'lft', 'limit_page_length': 1,
    })
    territories = call('frappe.client.get_list', {
        'doctype': 'Territory',
        'filters': [['is_group', '=', 0]],
        'fields': ['name'], 'order_by': 'lft', 'limit_page_length': 1,
    })
    if not groups or not territories:
        print('No non-group Customer Group / Territory.')
        sys.exit(3)
    SAFE_GROUP = groups[0]['name']
    SAFE_TERRITORY = territories[0]['name']

    batch_id = uuid.uuid4().hex[:8]
    states = ['Texas', 'Florida', 'New York', 'New Jersey']
    statuses = [
        'New', 'Need Follow-up', 'Diagnostics Offered', 'Waiting Prepayment',
        'Diagnostics Paid', 'Technician Assigned', 'Diagnostics In Progress',
        'Diagnosis Completed', 'Estimate Sent', 'Repair In Progress',
        'Repair Completed', 'Paid', 'Warranty Active', 'Closed', 'Lost',
    ]
    equipment = ['Combi Oven', 'Walk-in Cooler', 'Ice Machine', 'Dishwasher',
                 'Fryer', 'Mixer', 'Espresso Machine']
    urgencies = ['Emergency', 'Today', 'This Week', 'Scheduled']

    print(f"Seeding {args.count} synthetic Repair Jobs (batch={batch_id})...")
    created = 0
    failed = 0
    for i in range(args.count):
        suffix4 = ''.join(random.choices('0123456789', k=4))
        try:
            r = call('baro_crm.api.repair_job.create_repair_job', {'payload': {
                'customer_name': f"TEST-F-LOAD-{batch_id} #{i+1}",
                'caller_phone': '+1212' + str(500 + i % 500).zfill(3) + suffix4,
                'service_state': random.choice(states),
                'equipment_type': random.choice(equipment),
                'symptom': f"Synthetic symptom #{i+1}",
                'urgency': random.choice(urgencies),
            }})
            # Optionally advance status (skip for speed)
            created += 1
            if (i + 1) % 50 == 0:
                print(f"  {i+1}/{args.count}")
        except Exception as e:
            failed += 1
            if failed > 5:
                print(f"  too many failures ({failed}), aborting: {e}")
                sys.exit(4)
    print(f"\nDone. Created {created}/{args.count} (failed {failed}).")


def _cleanup_all(client):
    print('Cleaning all TEST-F-LOAD-* records...')
    custs = client.list_docs('Customer',
        filters=[['name', 'like', 'TEST-F-LOAD-%']],
        fields=['name'], limit=5000)
    print(f"  {len(custs)} TEST-F-LOAD-* customers to clean")
    for cust in custs:
        rjs = client.list_docs('Repair Job',
            filters=[['customer', '=', cust['name']]],
            fields=['name'], limit=50)
        for rj in rjs:
            try: client._request('DELETE', f'/api/resource/Repair Job/{rj["name"]}')
            except Exception: pass
        for ent in ('Contact', 'Address'):
            ents = client.list_docs(ent,
                filters=[
                    ['Dynamic Link', 'link_doctype', '=', 'Customer'],
                    ['Dynamic Link', 'link_name', '=', cust['name']],
                ], fields=['name'], limit=20)
            for e in ents:
                try: client._request('DELETE', f'/api/resource/{ent}/{e["name"]}')
                except Exception: pass
        try: client._request('DELETE', f'/api/resource/Customer/{cust["name"]}')
        except Exception as e: print(f"  warn: Customer {cust['name']}: {e}")
    print('Done.')


if __name__ == '__main__':
    main()
```

- [ ] **Step 3: Commit**

```powershell
git add scripts/verify_create_repair_job.py scripts/seed_synthetic_jobs.py
git -c user.name="Baro Service" -c user.email="baroservicellc@gmail.com" `
  commit -m "feat(scripts): F backend smoke (unique phone, --clean-stale) + synthetic seeder"
```

---

### Task 9: ★ CHECKPOINT — deploy Phase A, run backend smoke

**Files:** none changed (deploy + verification).

- [ ] **Step 1: Sync to server**

```powershell
cd "C:\Users\epmek\Documents"
scp -r "Erpnext Baro\baro_crm" admin1@100.127.172.110:/home/admin1/
scp "Erpnext Baro\scripts\verify_create_repair_job.py" admin1@100.127.172.110:/home/admin1/scripts/
scp "Erpnext Baro\scripts\seed_synthetic_jobs.py" admin1@100.127.172.110:/home/admin1/scripts/
```

- [ ] **Step 2: Run install.sh on the server**

```bash
cd ~/baro_crm
./install.sh
```

Watch for:
- step 4 (`bench migrate`): the 2 new Custom Fields should land. Look for `Updating customizations for Repair Job`.
- step 5/6: asset smoke green as before.

- [ ] **Step 3: Verify the new fields exist**

```bash
docker compose -f ~/frappe_docker/pwd.yml exec -T backend \
  bench --site frontend execute "frappe.get_meta('Repair Job').get_field('service_address_text').as_dict"
```

Expected: a dict with `fieldname: "service_address_text"`, `fieldtype: "Small Text"`.

```bash
docker compose -f ~/frappe_docker/pwd.yml exec -T backend \
  bench --site frontend execute "frappe.get_meta('Repair Job').get_field('address_needs_review').as_dict"
```

Expected: dict with `fieldname: "address_needs_review"`, `fieldtype: "Check"`.

- [ ] **Step 4: Run the smoke script (from the workstation, hitting the server)**

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
& "C:\Users\epmek\Documents\baro-call-sheet-bot\.venv\Scripts\python.exe" `
  .\scripts\verify_create_repair_job.py --execute
```

(If the venv path differs, use whichever Python has `requests` installed and can run the existing `erpnext_client.py`.)

Expected output (truncated):
```
Run prefix : TEST-F-2026-05-21-XXXXXXXX
Test phone : +1212555NNNN

  OK   find_dedup_warnings shape
  OK   create_repair_job minimal payload
  OK   active-RJ warning fires
  OK   incomplete address stored as text
  OK   bad customer_id rejected
  OK   phone multi-match blocks; force_create_new bypasses

Cleaning up...
  deleted RJ RJ-2026-NNNNN
  ...

All backend smoke checks passed.
```

- [ ] **Step 5: ★ Wait for user**

Tell the user: *"Phase A green. Backend endpoints + helpers + custom fields + smoke all pass. OK to start Phase B (cockpit refactors + audit polish)?"*

---

## Phase B — Cockpit refactors + audit polish

### Task 10: Bug 1.1 fix — restore the status popover

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`

The current selector `.pop-item[data-status]` matches nothing (real popover items use `data-action`/`data-target`; drag-popover items use `data-drag-action`). Change to: match `.pop-item` that has a `data-action` attribute AND does NOT have `data-drag-action`.

- [ ] **Step 1: Find the selector line**

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
```

In `baro_crm/baro_crm/public/js/cockpit.js`, search for `.pop-item[data-status]`. It appears once.

- [ ] **Step 2: Replace the selector**

Replace the line:
```javascript
      const popItem = e.target.closest('.pop-item[data-status]');
```
with:
```javascript
      const popItem = e.target.closest('.pop-item[data-action]:not([data-drag-action])');
```

- [ ] **Step 3: Commit**

```powershell
git add baro_crm/baro_crm/public/js/cockpit.js
git -c user.name="Baro Service" -c user.email="baroservicellc@gmail.com" `
  commit -m "fix(cockpit): bug 1.1 — restore status popover (selector now matches data-action items)"
```

---

### Task 11: Extract `installFocusTrap` helper and apply to inspector

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`

- [ ] **Step 1: Find a stable insertion point**

Search for `// ---------------------------------------------------------------------------\n  // Section 16: Drag/drop` — the drag/drop section header. Just BEFORE this comment (still inside the IIFE), insert the helper.

- [ ] **Step 2: Insert the helper**

```javascript
  // ---------------------------------------------------------------------------
  // Section 15b: Shared focus-trap helper (used by inspector and F drawer)
  // ---------------------------------------------------------------------------
  // Returns a cleanup function that removes the listeners.
  // Caller is responsible for installing/uninstalling on open/close.
  function installFocusTrap(rootEl, { initialFocus = null } = {}) {
    if (!rootEl) return () => {};

    function focusableNodes() {
      return Array.from(rootEl.querySelectorAll([
        'a[href]', 'button:not([disabled])', 'input:not([disabled])',
        'select:not([disabled])', 'textarea:not([disabled])',
        '[tabindex]:not([tabindex="-1"])',
      ].join(','))).filter(el => el.offsetParent !== null);
    }

    function onKey(e) {
      if (e.key !== 'Tab') return;
      const nodes = focusableNodes();
      if (nodes.length === 0) { e.preventDefault(); return; }
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener('keydown', onKey);

    // Move initial focus
    setTimeout(() => {
      const target = initialFocus || focusableNodes()[0] || rootEl;
      target.focus();
    }, 30);

    return function uninstall() {
      document.removeEventListener('keydown', onKey);
    };
  }
```

- [ ] **Step 3: Wire into inspector open/close**

Find the existing `openInspector(id)` function (search for `function openInspector(`). Inside it, after the drawer DOM is shown (e.g. after `$('#inspector').classList.add('open')`), add:

```javascript
    // Install focus trap on open; previous trap (if any) is cleared.
    if (state.inspectorTrapUninstall) state.inspectorTrapUninstall();
    state.inspectorTrapUninstall = installFocusTrap($('#inspector'), {
      initialFocus: $('#inspClose') || null,
    });
```

In `closeInspector()` (similar pattern), before clearing state, add:

```javascript
    if (state.inspectorTrapUninstall) {
      state.inspectorTrapUninstall();
      state.inspectorTrapUninstall = null;
    }
```

Also add `inspectorTrapUninstall: null,` to the `state` object initialization (search for `const state = {` and add the property near the other UI flags).

- [ ] **Step 4: Commit**

```powershell
git add baro_crm/baro_crm/public/js/cockpit.js
git -c user.name="Baro Service" -c user.email="baroservicellc@gmail.com" `
  commit -m "feat(cockpit): installFocusTrap helper + apply to inspector (audit bug 1.6)"
```

---

### Task 12: Fix `extractError` to decode Frappe `_server_messages`

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`

- [ ] **Step 1: Find the existing `extractError`**

Search for `function extractError` in `cockpit.js`. Replace its entire body with:

```javascript
  // Friendly mapping for common Frappe exception classes
  const ERROR_CLASS_MAP = {
    'PermissionError': "You don't have permission to do that.",
    'TimestampMismatchError': "Someone else just updated this. Click Refresh to see the latest.",
    'LinkValidationError': "A referenced record was not found.",
    'MandatoryError': "A required field is missing.",
    'DuplicateEntryError': "That record already exists.",
  };

  function extractError(e) {
    if (!e) return 'unknown error';

    // 1. Frappe REST/RPC: r._server_messages = '["{\\"message\\":\\"...\\"}"]'
    const sm = (e && e._server_messages)
            || (e && e.responseJSON && e.responseJSON._server_messages);
    if (sm) {
      try {
        const outer = JSON.parse(sm);
        const messages = [];
        for (const m of outer) {
          try {
            const inner = JSON.parse(m);
            if (inner && inner.message) messages.push(String(inner.message));
            else messages.push(String(m));
          } catch { messages.push(String(m)); }
        }
        if (messages.length) return messages.join(' · ');
      } catch { /* fall through */ }
    }

    // 2. Map known Frappe exception classes to friendly strings
    const exc = (e && e.exc_type) || (e && e.exception);
    if (exc && ERROR_CLASS_MAP[exc]) return ERROR_CLASS_MAP[exc];

    // 3. Last resort: e.message, e.exc, or stringify
    if (e.message) return String(e.message);
    if (e.exc) return String(e.exc).split('\n').slice(-2, -1).join('').trim() || String(e.exc);
    return String(e);
  }
```

- [ ] **Step 2: Commit**

```powershell
git add baro_crm/baro_crm/public/js/cockpit.js
git -c user.name="Baro Service" -c user.email="baroservicellc@gmail.com" `
  commit -m "fix(cockpit): extractError decodes _server_messages + maps known Frappe exc classes (audit 1.9)"
```

---

### Task 13: Extract `kanbanCardHtml(j)` and `renderRow(j)` helpers

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`

These extracted helpers make F's surgical post-create insert possible. No behavior change — pure refactor.

- [ ] **Step 1: Locate the kanban inner template**

In `renderKanban()`, find the `.map(j => { ... return \`<div class="kanban-card" ... \``. Cut the entire returned template literal into a new helper.

- [ ] **Step 2: Insert `kanbanCardHtml(j)` immediately before `renderKanban()`**

```javascript
  // Single-card kanban HTML — shared by renderKanban (full render) and F's surgical insert.
  function kanbanCardHtml(j) {
    const s = STATUS_MAP[j.status] || { color: 'slate' };
    const customerLabel = (j.customer || '').replace(/^DEMO\s*-\s*/i, '');
    return `
      <div class="kanban-card" data-id="${escapeHtml(j.name)}" data-status="${escapeHtml(j.status)}">
        <span class="kc-handle" data-stop aria-label="Drag ${escapeHtml(customerLabel || j.name)}" tabindex="-1">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <circle cx="9" cy="6" r="1.5"/><circle cx="9" cy="12" r="1.5"/><circle cx="9" cy="18" r="1.5"/>
            <circle cx="15" cy="6" r="1.5"/><circle cx="15" cy="12" r="1.5"/><circle cx="15" cy="18" r="1.5"/>
          </svg>
        </span>
        <div class="kc-body">
          <div class="kc-id">${escapeHtml(j.name)}</div>
          <div class="kc-title">${escapeHtml(customerLabel || j.name)}</div>
          <div class="kc-meta">
            <span class="status-pill s-${s.color}" data-stop><span class="dot" aria-hidden="true"></span>${escapeHtml(j.status)}</span>
          </div>
          <div class="kc-meta" style="margin-top:6px;">
            ${escapeHtml(j.equipment_type || '—')} • ${escapeHtml(j.service_state || j.area || '—')}
          </div>
          <div class="kc-foot">
            ${j.technician
              ? `<div class="avatar ${colorClass(j.technician)}" aria-hidden="true">${escapeHtml(initials(j.technician))}</div><span style="font-size:11.5px;color:var(--text-muted);">${escapeHtml(j.technician)}</span>`
              : `<span style="font-size:11px;color:var(--text-faint);font-style:italic;">Unassigned</span>`}
            <small>${escapeHtml(formatRelativeTime(j.modified))}</small>
          </div>
        </div>
      </div>`;
  }
```

- [ ] **Step 3: Replace the inline kanban template with a call**

In `renderKanban`, replace the inner `items.map(j => { ... return \`<div class="kanban-card" ...> ... </div>\`; }).join('')` with:

```javascript
            ${items.map(j => kanbanCardHtml(j)).join('')}
```

(Inside the column-body template literal interpolation.)

- [ ] **Step 4: Extract `renderRow(j)` for the list view**

Find the existing `renderTable()` function. Just like the kanban extraction, locate the row template inside its `.map(j => { return \`<tr ... \`; })`. Insert this helper before `renderTable`:

```javascript
  // Single-row HTML — shared by renderTable and F's surgical insert.
  function renderRow(j) {
    const s = STATUS_MAP[j.status] || { color: 'slate' };
    const techHtml = j.technician
      ? `<div class="tech-cell"><div class="avatar ${colorClass(j.technician)}" aria-hidden="true">${escapeHtml(initials(j.technician))}</div><span>${escapeHtml(j.technician)}</span></div>`
      : `<div class="tech-cell empty">Unassigned</div>`;
    const customer = j.customer || '(no customer)';
    const urgencyCls = (j.urgency || 'Unknown').replace(/\s+/g, '-');
    return `
      <tr data-id="${escapeHtml(j.name)}" class="${state.selectedId === j.name ? 'selected' : ''}" tabindex="0" role="button" aria-label="Open ${escapeHtml(customer)} — ${escapeHtml(j.status || 'New')}">
        <td>
          <div class="customer-cell">
            <div class="avatar ${colorClass(customer)}" aria-hidden="true">${escapeHtml(initials(customer))}</div>
            <div class="col">
              <strong>${escapeHtml(customer)}</strong>
              <small class="id-cell">${escapeHtml(j.name)}</small>
            </div>
          </div>
        </td>
        <td>
          <button class="status-pill s-${s.color}" type="button" data-status-btn data-stop aria-label="Status ${escapeHtml(j.status || '')}, click to change" aria-haspopup="listbox">
            <span class="dot" aria-hidden="true"></span>
            <span>${escapeHtml(j.status || 'New')}</span>
            <svg class="caret" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>
          </button>
        </td>
        <td><span style="font-family:'JetBrains Mono',monospace;font-size:12.5px;">${escapeHtml(j.caller_phone || '')}</span></td>
        <td>${escapeHtml(j.area || '')}</td>
        <td>${j.service_state ? `<span class="source-tag"><span class="dot" aria-hidden="true"></span>${escapeHtml(j.service_state)}</span>` : '<span style="color:var(--text-faint);font-style:italic;">—</span>'}</td>
        <td>${j.marketing_source ? `<span class="source-tag"><span class="dot" aria-hidden="true"></span>${escapeHtml(j.marketing_source)}</span>` : ''}</td>
        <td><div class="equipment-cell"><span class="urg ${escapeHtml(urgencyCls)}" aria-hidden="true"></span><span class="sr-only">Urgency ${escapeHtml(j.urgency || 'unknown')}.</span>${escapeHtml(j.equipment_type || '')}</div></td>
        <td>${techHtml}</td>
        <td><div class="time-cell">${escapeHtml(formatDateTime(j.modified))}<small>${escapeHtml(formatRelativeTime(j.modified))} ago</small></div></td>
      </tr>
    `;
  }
```

- [ ] **Step 5: Replace inline row template with a call**

In `renderTable`, replace the inner `state.jobs.map(...)` body that returns the row template with:

```javascript
    tbody.innerHTML = rows.map(j => renderRow(j)).join('');
```

(Where `rows` is the existing filtered/searched list.)

- [ ] **Step 6: Commit**

```powershell
git add baro_crm/baro_crm/public/js/cockpit.js
git -c user.name="Baro Service" -c user.email="baroservicellc@gmail.com" `
  commit -m "refactor(cockpit): extract kanbanCardHtml + renderRow (enables F surgical insert)"
```

---

### Task 14: Add `state.jobsById` map + replace `Array.find` call sites

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`

- [ ] **Step 1: Add to the state object**

Find `const state = {` (top of section 2). Add `jobsById: {},` next to `jobs: [],`:

```javascript
  const state = {
    jobs: [],
    jobsById: {},                          // NEW — O(1) lookups, rebuilt on every loadAll
    stateCounts: { All: 0, Texas: 0, Florida: 0, 'New York': 0, 'New Jersey': 0 },
    ...
  };
```

- [ ] **Step 2: Rebuild `jobsById` on every `loadAll`**

In `loadAll`, find `state.jobs = jobs || [];` and immediately after it add:

```javascript
      state.jobsById = Object.create(null);
      for (const j of state.jobs) state.jobsById[j.name] = j;
```

- [ ] **Step 3: Replace `Array.find` call sites**

Search the file for `state.jobs.find(`. Replace each occurrence:
```javascript
const j = state.jobs.find(x => x.name === id);
```
with:
```javascript
const j = state.jobsById[id];
```

Verify behavior is identical: both return `undefined` for unknown id.

- [ ] **Step 4: Commit**

```powershell
git add baro_crm/baro_crm/public/js/cockpit.js
git -c user.name="Baro Service" -c user.email="baroservicellc@gmail.com" `
  commit -m "perf(cockpit): state.jobsById map; replace 14 Array.find call sites with O(1) lookup"
```

---

### Task 15: Misc audit polish — drag move guard, popover focus restore, contrast bump, drag handle title

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`
- Modify: `baro_crm/baro_crm/public/css/cockpit.css`

Four small fixes in one commit.

- [ ] **Step 1: handleDragMove null-guard**

In `cockpit.js`, find `function handleDragMove`. Replace its final return with:

```javascript
    return !!(evt.to && evt.to.classList.contains('drop-valid'));
```

- [ ] **Step 2: closeStatusPopover restores focus**

Find `function closeStatusPopover`. Replace its body with:

```javascript
  function closeStatusPopover() {
    const trigger = state.statusPopoverTrigger;
    $('#statusPopover').classList.remove('open');
    state.statusPopoverFor = null;
    state.statusPopoverTrigger = null;
    if (trigger && document.body.contains(trigger)) {
      try { trigger.focus(); } catch (e) {}
    }
  }
```

Then find `openStatusPopover` (the inspector/list version, not the drag one). After it sets `state.statusPopoverFor = jobId;`, add:

```javascript
    state.statusPopoverTrigger = targetEl || null;
```

Add `statusPopoverTrigger: null,` to the `state` initialization.

- [ ] **Step 3: --text-faint contrast bump**

In `cockpit.css`, search for `--text-faint:`. Replace the value:

From:
```css
  --text-faint: #94a3b8;
```
To:
```css
  --text-faint: #7c8aa1;   /* AA contrast on white (was #94a3b8 = 3.0:1) */
```

- [ ] **Step 4: Drag handle title**

In the `kanbanCardHtml(j)` helper (Task 13), find:
```html
<span class="kc-handle" data-stop aria-label="Drag ${escapeHtml(customerLabel || j.name)}" tabindex="-1">
```
Replace with:
```html
<span class="kc-handle" data-stop aria-label="Drag ${escapeHtml(customerLabel || j.name)}" title="Drag to change status" tabindex="-1">
```

- [ ] **Step 5: Commit**

```powershell
git add baro_crm/baro_crm/public/js/cockpit.js baro_crm/baro_crm/public/css/cockpit.css
git -c user.name="Baro Service" -c user.email="baroservicellc@gmail.com" `
  commit -m "polish(cockpit): drag-move null-guard, popover focus return, --text-faint contrast, drag handle title"
```

---

### Task 16: Update `loadAll` for new `get_jobs` response shape + pre-group kanban

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`

- [ ] **Step 1: Update `loadAll` to handle the new shape**

Find `async function loadAll`. Replace its body with:

```javascript
  async function loadAll({ refreshCounts = true, offset = 0, append = false } = {}) {
    try {
      const args = { state: state.activeState, search: state.search, offset, limit: 500 };
      const [jobsResponse, counts] = await Promise.all([
        api.getJobs(args),
        refreshCounts ? api.stateCounts() : Promise.resolve(state.stateCounts),
      ]);
      const newJobs = (jobsResponse && jobsResponse.jobs) || [];

      if (append) {
        state.jobs = state.jobs.concat(newJobs);
      } else {
        state.jobs = newJobs;
      }
      state.jobsById = Object.create(null);
      for (const j of state.jobs) state.jobsById[j.name] = j;

      state.totalJobs = jobsResponse ? jobsResponse.total : null;     // may be null when searching
      state.hasMoreJobs = !!(jobsResponse && jobsResponse.has_more);

      if (counts) state.stateCounts = counts;
      renderStateTabs();
      renderTable();
      if (state.activeView === 'kanban') renderKanban();
      renderLoadMore();
    } catch (e) {
      console.error('loadAll failed', e);
      toast('Failed to load Repair Jobs. ' + extractError(e), 'err');
    }
  }
```

- [ ] **Step 2: Add `renderLoadMore` stub**

Insert immediately after `loadAll`:

```javascript
  // Wired up properly in Task 19 (Phase C). Stub for now.
  function renderLoadMore() {}
```

- [ ] **Step 3: Add `totalJobs` + `hasMoreJobs` to state init**

In the `const state = {` block, add:
```javascript
    totalJobs: null,
    hasMoreJobs: false,
```

- [ ] **Step 4: Pre-group by status in `renderKanban`**

Find `function renderKanban`. At the very start (after the early-return on missing `#kanban`), add:

```javascript
    const byStatus = Object.create(null);
    for (const j of state.jobs) {
      (byStatus[j.status] = byStatus[j.status] || []).push(j);
    }
```

Then in the column-body template literal, replace:
```javascript
const items = state.jobs.filter(j => col.keys.includes(j.status));
```
with:
```javascript
const items = [];
for (const k of col.keys) {
  if (byStatus[k]) items.push(...byStatus[k]);
}
```

- [ ] **Step 5: Commit**

```powershell
git add baro_crm/baro_crm/public/js/cockpit.js
git -c user.name="Baro Service" -c user.email="baroservicellc@gmail.com" `
  commit -m "perf(cockpit): loadAll handles {jobs,total,has_more} shape; renderKanban pre-groups by status"
```

---

### Task 17: ★ CHECKPOINT — deploy Phase B, verify no regression

- [ ] **Step 1: Sync + install**

```powershell
cd "C:\Users\epmek\Documents"
scp -r "Erpnext Baro\baro_crm" admin1@100.127.172.110:/home/admin1/
```

```bash
cd ~/baro_crm
./install.sh
```

- [ ] **Step 2: Browser verification**

Open `http://100.127.172.110:8080/repair-jobs`. Verify:

- List view loads
- Kanban view loads
- Click a row's status pill → popover opens → click any transition → status changes (Bug 1.1 fix — this is THE critical regression test)
- Click any card to open inspector → Tab cycles within inspector (focus trap working)
- Open devtools console → no JS errors
- Drag a kanban card → behaves as before

- [ ] **Step 3: ★ Wait for user**

Tell the user: *"Phase B green. Status popover works (Bug 1.1 fixed), focus trap on inspector, extractError decodes Frappe messages, kanbanCardHtml/renderRow extracted, jobsById map in place. OK to start Phase C (scale handling)?"*

---

## Phase C — Scale handling

### Task 18: Kanban natural-height + sticky column heads

**Files:**
- Modify: `baro_crm/baro_crm/public/css/cockpit.css`

- [ ] **Step 1: Remove column max-height and column-body internal scroll**

Find these CSS rules in `cockpit.css`:

```css
.baro-cockpit .kanban-col { ... max-height: 100%; ... }
.baro-cockpit .kanban-col-body { ... overflow-y: auto; ... }
```

For `.kanban-col`: delete the `max-height: 100%;` declaration (leave the rest of the rule).
For `.kanban-col-body`: delete the `overflow-y: auto;` declaration.

- [ ] **Step 2: Update `.kanban-wrap` overflow**

Find `.baro-cockpit .kanban-wrap`. Replace its overflow rules with:

```css
.baro-cockpit .kanban-wrap { overflow-x: auto; overflow-y: visible; padding: 0 22px 22px; min-height: 0; }
```

- [ ] **Step 3: Make column heads sticky**

Find `.baro-cockpit .kanban-col-head`. Add `position: sticky; top: 0; z-index: 2; background: var(--surface-2);` to the rule. The full rule should now read:

```css
.baro-cockpit .kanban-col-head {
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 8px;
  position: sticky; top: 0; z-index: 2;
  background: var(--surface-2);
}
```

- [ ] **Step 4: Commit**

```powershell
git add baro_crm/baro_crm/public/css/cockpit.css
git -c user.name="Baro Service" -c user.email="baroservicellc@gmail.com" `
  commit -m "feat(cockpit): kanban columns natural-height + sticky column heads (page scrolls vertically)"
```

---

### Task 19: "Load 500 more" footer + handler

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`
- Modify: `baro_crm/baro_crm/public/css/cockpit.css`

- [ ] **Step 1: Add the load-more footer DOM into the shell**

In `renderShell`, find the closing `</div>` of `<main class="main" ...>` (i.e. the line right before `</main>`). Just before that, insert:

```html
        <div class="load-more-footer" id="loadMoreFooter" style="display:none;">
          <button type="button" class="btn btn-outline" id="btnLoadMore">Load 500 more</button>
          <span class="load-more-summary" id="loadMoreSummary"></span>
        </div>
```

- [ ] **Step 2: Replace the `renderLoadMore` stub with the real renderer**

```javascript
  function renderLoadMore() {
    const footer = $('#loadMoreFooter');
    const summary = $('#loadMoreSummary');
    if (!footer || !summary) return;
    if (!state.hasMoreJobs) {
      footer.style.display = 'none';
      return;
    }
    footer.style.display = '';
    const shown = state.jobs.length;
    if (state.totalJobs != null) {
      summary.textContent = `Showing ${shown.toLocaleString()} of ${state.totalJobs.toLocaleString()}`;
    } else {
      summary.textContent = `Showing ${shown.toLocaleString()} (search active — total unknown)`;
    }
  }
```

- [ ] **Step 3: Wire the click handler in `bindEvents`**

Search for `function bindEvents`. Inside the main delegated click handler, just before its closing `});`, add:

```javascript
    if (e.target.closest('#btnLoadMore')) {
      loadAll({ refreshCounts: false, offset: state.jobs.length, append: true });
      return;
    }
```

- [ ] **Step 4: Style the footer**

In `cockpit.css`, append at the end of the file:

```css
/* -- Load-more footer -- */
.baro-cockpit .load-more-footer {
  display: flex; align-items: center; gap: 12px;
  justify-content: center;
  padding: 14px 22px 22px;
  border-top: 1px solid var(--border);
  background: var(--surface);
}
.baro-cockpit .load-more-summary {
  font-size: 12.5px; color: var(--text-muted);
}
```

- [ ] **Step 5: Commit**

```powershell
git add baro_crm/baro_crm/public/js/cockpit.js baro_crm/baro_crm/public/css/cockpit.css
git -c user.name="Baro Service" -c user.email="baroservicellc@gmail.com" `
  commit -m "feat(cockpit): Load 500 more footer + handler (pagination)"
```

---

### Task 20: ★ CHECKPOINT — deploy Phase C, verify scrolling at scale

- [ ] **Step 1: Sync + install**

```powershell
cd "C:\Users\epmek\Documents"
scp -r "Erpnext Baro\baro_crm" admin1@100.127.172.110:/home/admin1/
```

```bash
cd ~/baro_crm
./install.sh
```

- [ ] **Step 2: Seed synthetic jobs (server side, BARO_ALLOW_SYNTHETIC required)**

ON THE SERVER (via SSH):

```bash
BARO_ALLOW_SYNTHETIC=1 python3 ~/scripts/seed_synthetic_jobs.py --count 600 --execute
```

(If you don't have a Python venv on the server with the right deps, run from your workstation against the Tailscale IP — same syntax, same env var.)

- [ ] **Step 3: Browser verification**

Open `http://100.127.172.110:8080/repair-jobs`. Verify:

- List view shows 500 rows. A "Load 500 more — Showing 500 of 6XX" footer appears below.
- Click "Load 500 more" → all rows appear; footer hides.
- Switch to Kanban view. Columns natural-height; total page scrolls vertically.
- Scroll down inside a tall column — column header stays pinned at top.

- [ ] **Step 4: Clean up synthetic data when done**

```bash
BARO_ALLOW_SYNTHETIC=1 python3 ~/scripts/seed_synthetic_jobs.py --cleanup --execute
```

- [ ] **Step 5: ★ Wait for user**

Tell the user: *"Phase C green. Kanban scrolls vertically with sticky heads, Load More works, no degradation at 600 rows. OK to start Phase D (the actual drawer)?"*

---

## Phase D — Drawer

### Task 21: Drawer DOM scaffold + open/close state + topbar wiring

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`

- [ ] **Step 1: Add drawer state fields**

In the `const state = {` block, add:

```javascript
    createOpen: false,
    createDraft: null,           // { customer_name?, customer_id?, caller_phone?, ... }
    createDedupWarnings: null,
    createForceNew: false,
    createSubmitting: false,
    createTrapUninstall: null,
    customerLookupCache: new Map(),
```

- [ ] **Step 2: Insert the drawer DOM into renderShell**

In `renderShell`, find the existing `<aside class="inspector" id="inspector" ...>`. Immediately AFTER the closing `</aside>` of the inspector, insert:

```html
      <aside class="create-drawer" id="createDrawer" role="dialog" aria-modal="true" aria-labelledby="createDrawerTitle" aria-hidden="true" tabindex="-1">
        <div class="insp-head">
          <div class="col-main">
            <div class="insp-id">New Repair Job</div>
            <h2 id="createDrawerTitle">Create a Repair Job</h2>
            <div class="insp-meta">
              <span>Required fields are marked *</span>
            </div>
          </div>
          <button class="insp-close" id="createDrawerClose" aria-label="Close drawer" title="Close (Esc)">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="insp-body" id="createDrawerBody">
          <div id="dedupBanners"></div>
          <form id="createRepairJobForm" autocomplete="off" novalidate></form>
        </div>
        <div class="insp-actionbar">
          <button class="btn btn-outline" type="button" id="btnCreateCancel">Cancel</button>
          <button class="btn btn-primary" type="button" id="btnCreateSubmit" disabled>Create Repair Job</button>
        </div>
      </aside>
```

- [ ] **Step 3: Wire the topbar button to open the drawer**

In `renderShell`, find the existing `<a class="btn btn-primary" href="/app/repair-job/new...">` (the "+ New Repair Job" topbar button). Replace it with:

```html
            <button class="btn btn-primary" type="button" id="btnOpenCreateDrawer">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              New Repair Job
            </button>
            <a class="btn btn-ghost" href="/app/repair-job/new" target="_blank" rel="noopener" title="Open ERPNext form (advanced)" style="font-size:11.5px;color:var(--text-faint);margin-left:4px;">⤴</a>
```

The second `<a>` is a fallback link to the stock ERPNext form for advanced cases.

- [ ] **Step 4: Insert open/close helpers**

Insert as a new section at the end of cockpit.js's main IIFE (before the boot function):

```javascript
  // ---------------------------------------------------------------------------
  // Section 18: Create Repair Job drawer
  // ---------------------------------------------------------------------------
  function openCreateDrawer() {
    if (state.selectedId) closeInspector();   // mutual exclusion
    state.createOpen = true;
    state.createDraft = { force_create_new: false };
    state.createForceNew = false;
    state.createDedupWarnings = null;
    state.createSubmitting = false;
    renderCreateForm();
    const drawer = $('#createDrawer');
    drawer.classList.add('open');
    drawer.setAttribute('aria-hidden', 'false');
    $('#inspOverlay').classList.add('open');
    if (state.createTrapUninstall) state.createTrapUninstall();
    state.createTrapUninstall = installFocusTrap(drawer, {
      initialFocus: drawer.querySelector('input[name="customer_name"]') || $('#createDrawerClose'),
    });
    // Disable the topbar button while drawer is open
    const btn = $('#btnOpenCreateDrawer');
    if (btn) btn.disabled = true;
  }

  function closeCreateDrawer({ force = false } = {}) {
    if (!state.createOpen) return;
    if (!force && createDirty()) {
      // Confirm dirty-close
      showConfirmDialog({
        title: 'Discard new Repair Job?',
        desc: 'Your changes will be lost.',
        okLabel: 'Discard',
      }).then(ok => { if (ok) closeCreateDrawer({ force: true }); });
      return;
    }
    state.createOpen = false;
    state.createDraft = null;
    state.createDedupWarnings = null;
    state.createForceNew = false;
    const drawer = $('#createDrawer');
    drawer.classList.remove('open');
    drawer.setAttribute('aria-hidden', 'true');
    if (!state.selectedId) $('#inspOverlay').classList.remove('open');
    if (state.createTrapUninstall) {
      state.createTrapUninstall();
      state.createTrapUninstall = null;
    }
    const btn = $('#btnOpenCreateDrawer');
    if (btn) btn.disabled = false;
  }

  function createDirty() {
    const d = state.createDraft || {};
    return !!(d.customer_name || d.caller_phone || d.equipment_type
              || d.symptom || d.service_address || d.internal_comment
              || d.service_state || d.urgency
              || d.business_phone_did || d.marketing_source
              || d.area);
  }

  // Stub — implemented in Task 23
  function renderCreateForm() {
    $('#createRepairJobForm').innerHTML = '<p>Form coming in Task 23.</p>';
  }
```

- [ ] **Step 5: Wire close + open click handlers**

In `bindEvents`, inside the main delegated click handler, add (in any order, but before the catch-all close):

```javascript
    if (e.target.closest('#btnOpenCreateDrawer')) {
      openCreateDrawer();
      return;
    }
    if (e.target.closest('#createDrawerClose') || e.target.closest('#btnCreateCancel')) {
      closeCreateDrawer();
      return;
    }
```

Also extend the inspector-overlay click handler. Find:

```javascript
    if (e.target.closest('#inspOverlay') && !e.target.closest('.inspector')) {
      closeInspector();
      return;
    }
```

Replace with:

```javascript
    if (e.target.closest('#inspOverlay') && !e.target.closest('.inspector') && !e.target.closest('.create-drawer')) {
      if (state.createOpen) closeCreateDrawer();
      else closeInspector();
      return;
    }
```

Then in the Esc handler (search for `if (e.key === 'Escape')`):

```javascript
      if (state.createOpen) { closeCreateDrawer(); return; }
```

(Place this BEFORE the existing `closeStatusPopover` and inspector-close lines.)

- [ ] **Step 6: Mutual exclusion the other direction**

In `openInspector`, at the start (after the `state.selectedId` guard), add:

```javascript
    if (state.createOpen) closeCreateDrawer({ force: true });
```

- [ ] **Step 7: Commit**

```powershell
git add baro_crm/baro_crm/public/js/cockpit.js
git -c user.name="Baro Service" -c user.email="baroservicellc@gmail.com" `
  commit -m "feat(drawer): scaffold open/close + topbar wiring + mutual exclusion with inspector"
```

---

### Task 22: Drawer CSS

**Files:**
- Modify: `baro_crm/baro_crm/public/css/cockpit.css`

- [ ] **Step 1: Append drawer styles at end of cockpit.css**

```css
/* -- Create Repair Job drawer (mirrors inspector dimensions/animation) -- */
.baro-cockpit .create-drawer {
  position: fixed;
  top: 0; right: 0; bottom: 0;
  width: 560px; max-width: 95vw;
  background: var(--surface);
  box-shadow: var(--shadow-lg);
  display: flex; flex-direction: column;
  z-index: 200;
  transform: translateX(100%);
  transition: transform .25s ease-out;
}
.baro-cockpit .create-drawer.open { transform: translateX(0); }
.baro-cockpit .create-drawer .insp-body { padding-bottom: 8px; }
.baro-cockpit #createRepairJobForm { display: grid; gap: 14px; padding-top: 4px; }
.baro-cockpit #createRepairJobForm .field-row { display: grid; gap: 4px; }
.baro-cockpit #createRepairJobForm label { font-size: 12px; color: var(--text-muted); font-weight: 500; }
.baro-cockpit #createRepairJobForm label .required-mark { color: var(--c-rose); margin-left: 2px; }
.baro-cockpit #createRepairJobForm input[type="text"],
.baro-cockpit #createRepairJobForm input[type="tel"],
.baro-cockpit #createRepairJobForm select,
.baro-cockpit #createRepairJobForm textarea {
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
  font-family: inherit;
  background: var(--surface);
  color: var(--text);
  outline: none;
  transition: border-color .12s;
}
.baro-cockpit #createRepairJobForm input:focus,
.baro-cockpit #createRepairJobForm select:focus,
.baro-cockpit #createRepairJobForm textarea:focus {
  border-color: var(--brand);
  box-shadow: 0 0 0 2px var(--brand-50);
}
.baro-cockpit #createRepairJobForm textarea { min-height: 60px; resize: vertical; }
.baro-cockpit #createRepairJobForm .field-row.invalid input,
.baro-cockpit #createRepairJobForm .field-row.invalid select,
.baro-cockpit #createRepairJobForm .field-row.invalid textarea {
  border-color: var(--c-rose);
}
.baro-cockpit #createRepairJobForm .field-error {
  font-size: 11.5px; color: var(--c-rose); margin-top: 2px;
}
.baro-cockpit .optional-fields-toggle {
  display: flex; align-items: center; gap: 6px;
  background: none; border: none; padding: 4px 0;
  color: var(--text-muted); font-size: 12.5px; cursor: pointer;
}
.baro-cockpit .optional-fields { display: none; }
.baro-cockpit .optional-fields.expanded { display: grid; gap: 14px; }

/* -- Customer typeahead panel -- */
.baro-cockpit .typeahead-host { position: relative; }
.baro-cockpit .typeahead-panel {
  position: absolute; left: 0; right: 0; top: 100%;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  box-shadow: var(--shadow);
  margin-top: 4px;
  max-height: 260px; overflow: auto;
  z-index: 10;
  display: none;
}
.baro-cockpit .typeahead-panel.open { display: block; }
.baro-cockpit .typeahead-item {
  display: block; width: 100%;
  padding: 8px 10px;
  background: none; border: none; text-align: left;
  font-size: 13px; color: var(--text);
  cursor: pointer; line-height: 1.3;
}
.baro-cockpit .typeahead-item:hover,
.baro-cockpit .typeahead-item.active { background: var(--brand-50); }
.baro-cockpit .typeahead-item.system { color: var(--text-muted); font-style: italic; border-top: 1px solid var(--border); }
.baro-cockpit .typeahead-locked {
  display: flex; align-items: center; gap: 6px;
  background: var(--brand-50); color: var(--brand-700);
  padding: 7px 10px;
  border-radius: 6px;
  font-size: 13px; font-weight: 500;
}
.baro-cockpit .typeahead-locked .unlock {
  background: none; border: none;
  color: var(--brand-700);
  cursor: pointer; padding: 0 4px;
  font-size: 14px;
}

/* -- Dedup banners -- */
.baro-cockpit .dedup-banner {
  padding: 10px 12px;
  border-radius: 6px;
  font-size: 12.5px;
  margin-bottom: 10px;
  border: 1px solid;
}
.baro-cockpit .dedup-banner.info { background: #f1f3f6; border-color: var(--border-strong); color: var(--text); }
.baro-cockpit .dedup-banner.warn { background: #fef3c7; border-color: #fde68a; color: #92400e; }
.baro-cockpit .dedup-banner.block { background: #fee2e2; border-color: #fecaca; color: #b91c1c; }
.baro-cockpit .dedup-banner .actions { margin-top: 6px; display: flex; gap: 6px; flex-wrap: wrap; }
.baro-cockpit .dedup-banner .btn-mini {
  padding: 3px 8px;
  font-size: 11.5px;
  border-radius: 4px;
  border: 1px solid currentColor;
  background: transparent;
  color: inherit;
  cursor: pointer;
}
.baro-cockpit .dedup-banner .btn-mini:hover { background: rgba(0,0,0,0.05); }
.baro-cockpit .force-create-new-row {
  margin-top: 8px;
  display: flex; align-items: center; gap: 6px;
  font-size: 12.5px;
}

/* -- Empty-table CTA -- */
.baro-cockpit .empty-table .empty-actions { margin-top: 10px; }
```

- [ ] **Step 2: Commit**

```powershell
git add baro_crm/baro_crm/public/css/cockpit.css
git -c user.name="Baro Service" -c user.email="baroservicellc@gmail.com" `
  commit -m "feat(drawer): drawer + typeahead + dedup banner CSS"
```

---

### Task 23: Render form fields + bind input events

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`

- [ ] **Step 1: Replace the `renderCreateForm` stub with the real version**

Find the stub `function renderCreateForm()` from Task 21 and replace with:

```javascript
  function renderCreateForm() {
    const f = $('#createRepairJobForm');
    if (!f) return;
    const d = state.createDraft || {};
    const lockedCustomer = !!d.customer_id;

    f.innerHTML = `
      <!-- Customer (typeahead) -->
      <div class="field-row" data-field="customer">
        <label for="cr_customer">Customer <span class="required-mark">*</span></label>
        <div class="typeahead-host">
          ${lockedCustomer ? `
            <div class="typeahead-locked">
              <span>✓ ${escapeHtml(d.customer_name || d.customer_id)}</span>
              <button type="button" class="unlock" id="cr_customer_unlock" aria-label="Unlock and re-search">×</button>
            </div>
          ` : `
            <input type="text" id="cr_customer" name="customer_name" value="${escapeHtml(d.customer_name || '')}" placeholder="Type business name…" autocomplete="off">
            <div class="typeahead-panel" id="cr_customer_panel" role="listbox"></div>
          `}
        </div>
        <div class="field-error" id="err_customer" style="display:none;">Required</div>
      </div>

      <!-- Caller phone -->
      <div class="field-row" data-field="caller_phone">
        <label for="cr_phone">Caller phone <span class="required-mark">*</span></label>
        <input type="tel" id="cr_phone" name="caller_phone" value="${escapeHtml(d.caller_phone || '')}" placeholder="+1 212 555 0101 — any format">
        <div class="field-error" id="err_caller_phone" style="display:none;">Required</div>
      </div>

      <!-- Service state -->
      <div class="field-row" data-field="service_state">
        <label for="cr_state">Service state <span class="required-mark">*</span></label>
        <select id="cr_state" name="service_state">
          <option value="">— pick —</option>
          <option value="Texas"     ${d.service_state === 'Texas' ? 'selected' : ''}>Texas</option>
          <option value="Florida"   ${d.service_state === 'Florida' ? 'selected' : ''}>Florida</option>
          <option value="New York"  ${d.service_state === 'New York' ? 'selected' : ''}>New York</option>
          <option value="New Jersey" ${d.service_state === 'New Jersey' ? 'selected' : ''}>New Jersey</option>
        </select>
        <div class="field-error" id="err_service_state" style="display:none;">Required</div>
      </div>

      <!-- Equipment -->
      <div class="field-row" data-field="equipment_type">
        <label for="cr_equip">Equipment type <span class="required-mark">*</span></label>
        <input type="text" id="cr_equip" name="equipment_type" value="${escapeHtml(d.equipment_type || '')}" placeholder="Combi Oven / Walk-in Cooler / …">
        <div class="field-error" id="err_equipment_type" style="display:none;">Required</div>
      </div>

      <!-- Symptom -->
      <div class="field-row" data-field="symptom">
        <label for="cr_symptom">Symptom <span class="required-mark">*</span></label>
        <textarea id="cr_symptom" name="symptom" rows="2" placeholder="What's wrong with the equipment?">${escapeHtml(d.symptom || '')}</textarea>
        <div class="field-error" id="err_symptom" style="display:none;">Required</div>
      </div>

      <!-- Urgency -->
      <div class="field-row" data-field="urgency">
        <label for="cr_urgency">Urgency <span class="required-mark">*</span></label>
        <select id="cr_urgency" name="urgency">
          <option value="">— pick —</option>
          <option value="Emergency"  ${d.urgency === 'Emergency' ? 'selected' : ''}>Emergency</option>
          <option value="Today"      ${d.urgency === 'Today' ? 'selected' : ''}>Today</option>
          <option value="This Week"  ${d.urgency === 'This Week' ? 'selected' : ''}>This Week</option>
          <option value="Scheduled"  ${d.urgency === 'Scheduled' ? 'selected' : ''}>Scheduled</option>
          <option value="Unknown"    ${d.urgency === 'Unknown' ? 'selected' : ''}>Unknown</option>
        </select>
        <div class="field-error" id="err_urgency" style="display:none;">Required</div>
      </div>

      <!-- Optional section toggle -->
      <button type="button" class="optional-fields-toggle" id="cr_optional_toggle" aria-expanded="${d.__optionalOpen ? 'true' : 'false'}">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <polyline points="${d.__optionalOpen ? '6 9 12 15 18 9' : '9 6 15 12 9 18'}"/>
        </svg>
        Optional fields
      </button>
      <div class="optional-fields ${d.__optionalOpen ? 'expanded' : ''}" id="cr_optional">
        <div class="field-row"><label for="cr_did">Business DID</label>
          <input type="text" id="cr_did" name="business_phone_did" value="${escapeHtml(d.business_phone_did || '')}"></div>
        <div class="field-row"><label for="cr_source">Marketing source</label>
          <input type="text" id="cr_source" name="marketing_source" value="${escapeHtml(d.marketing_source || '')}"></div>
        <div class="field-row"><label for="cr_area">Area (city/region)</label>
          <input type="text" id="cr_area" name="area" value="${escapeHtml(d.area || '')}"></div>
        <div class="field-row"><label for="cr_addr">Service address</label>
          <textarea id="cr_addr" name="service_address" rows="2" placeholder="e.g. 124 East 50th, New York, NY 10022">${escapeHtml(d.service_address || '')}</textarea></div>
        <div class="field-row"><label for="cr_note">Internal comment</label>
          <textarea id="cr_note" name="internal_comment" rows="2">${escapeHtml(d.internal_comment || '')}</textarea></div>
      </div>
    `;

    bindCreateFormEvents();
    updateSubmitEnabled();
  }

  function bindCreateFormEvents() {
    const f = $('#createRepairJobForm');
    if (!f) return;

    // Generic input → save to draft + revalidate submit
    f.addEventListener('input', (e) => {
      const name = e.target.name;
      if (!name) return;
      const d = state.createDraft || (state.createDraft = {});
      d[name] = e.target.value;
      updateSubmitEnabled();
      // Clear field error on edit
      const err = $('#err_' + name);
      if (err) err.style.display = 'none';
      const row = e.target.closest('.field-row');
      if (row) row.classList.remove('invalid');

      // Trigger typeahead / dedup updates
      if (name === 'customer_name') triggerCustomerTypeahead(e.target.value);
      if (name === 'caller_phone') triggerPhoneDedupCheck();
    }, { once: false });

    // Optional fields toggle
    const tgl = $('#cr_optional_toggle');
    if (tgl) tgl.addEventListener('click', () => {
      const d = state.createDraft || (state.createDraft = {});
      d.__optionalOpen = !d.__optionalOpen;
      const panel = $('#cr_optional');
      const svg = tgl.querySelector('polyline');
      if (d.__optionalOpen) { panel.classList.add('expanded'); if (svg) svg.setAttribute('points', '6 9 12 15 18 9'); }
      else { panel.classList.remove('expanded'); if (svg) svg.setAttribute('points', '9 6 15 12 9 18'); }
      tgl.setAttribute('aria-expanded', d.__optionalOpen ? 'true' : 'false');
    });

    // Unlock customer pick
    const unlock = $('#cr_customer_unlock');
    if (unlock) unlock.addEventListener('click', () => {
      const d = state.createDraft;
      delete d.customer_id;
      // keep customer_name as a starting point for re-search
      renderCreateForm();
      setTimeout(() => $('#cr_customer')?.focus(), 0);
    });
  }

  function updateSubmitEnabled() {
    const d = state.createDraft || {};
    const required = ['caller_phone', 'service_state', 'equipment_type', 'symptom', 'urgency'];
    const customerOk = !!(d.customer_id || (d.customer_name && d.customer_name.trim()));
    const requiredOk = required.every(k => (d[k] || '').toString().trim());
    const blockedByDedup = !!(state.createDedupWarnings
        && state.createDedupWarnings.phone_multi_match
        && state.createDedupWarnings.phone_multi_match.length > 1
        && !state.createForceNew
        && !d.customer_id);
    const enable = customerOk && requiredOk && !blockedByDedup && !state.createSubmitting;
    const btn = $('#btnCreateSubmit');
    if (btn) btn.disabled = !enable;
  }

  // Stubs — implemented in Tasks 24 + 26
  function triggerCustomerTypeahead(q) {}
  function triggerPhoneDedupCheck() {}
```

- [ ] **Step 2: Commit**

```powershell
git add baro_crm/baro_crm/public/js/cockpit.js
git -c user.name="Baro Service" -c user.email="baroservicellc@gmail.com" `
  commit -m "feat(drawer): render form fields + bind input events + submit-enable logic"
```

---

### Task 24: Customer typeahead

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`

- [ ] **Step 1: Replace `triggerCustomerTypeahead` stub**

```javascript
  let customerTypeaheadTimer = null;
  function triggerCustomerTypeahead(q) {
    clearTimeout(customerTypeaheadTimer);
    customerTypeaheadTimer = setTimeout(() => doCustomerTypeahead(q), 200);
  }

  async function doCustomerTypeahead(q) {
    const panel = $('#cr_customer_panel');
    if (!panel) return;
    const query = (q || '').trim();
    if (query.length < 2) {
      panel.classList.remove('open');
      panel.innerHTML = '';
      return;
    }

    let results;
    if (state.customerLookupCache.has(query)) {
      results = state.customerLookupCache.get(query);
    } else {
      try {
        results = await api.searchLink('Customer', query);
      } catch (e) {
        console.error('typeahead failed', e);
        return;
      }
      state.customerLookupCache.set(query, results);
    }

    const d = state.createDraft || {};
    const items = (results || []).slice(0, 8).map(r => `
      <button type="button" class="typeahead-item" role="option"
              data-customer-id="${escapeHtml(r.value)}"
              data-customer-name="${escapeHtml(r.label || r.value)}">
        ${escapeHtml(r.label || r.value)}
      </button>
    `).join('');

    let system = '';
    if (query.length >= 3) {
      system += `<button type="button" class="typeahead-item system" data-create-new="1">
        + Create new "${escapeHtml(query)}"
      </button>`;
    }
    if (d.caller_phone && d.caller_phone.trim()) {
      system += `<button type="button" class="typeahead-item system" data-use-phone="1">
        Use phone ${escapeHtml(d.caller_phone)} — no name
      </button>`;
    }

    panel.innerHTML = items + system;
    panel.classList.add('open');

    // Bind per-item clicks (one-shot — re-runs on next render)
    panel.querySelectorAll('.typeahead-item').forEach(el => {
      el.addEventListener('click', () => {
        if (el.dataset.createNew) {
          // Keep typed name as-is, no customer_id
          panel.classList.remove('open');
          return;
        }
        if (el.dataset.usePhone) {
          state.createDraft.customer_name = '';
          delete state.createDraft.customer_id;
          renderCreateForm();
          return;
        }
        state.createDraft.customer_id = el.dataset.customerId;
        state.createDraft.customer_name = el.dataset.customerName;
        renderCreateForm();
        // Trigger dedup check now that customer_id is known
        triggerPhoneDedupCheck();
      });
    });
  }
```

- [ ] **Step 2: Close the panel on outside click**

In `bindEvents`, after the existing close-popover-on-outside-click logic, add:

```javascript
    if (!e.target.closest('#cr_customer_panel') && !e.target.closest('#cr_customer')) {
      const panel = $('#cr_customer_panel');
      if (panel) panel.classList.remove('open');
    }
```

- [ ] **Step 3: Commit**

```powershell
git add baro_crm/baro_crm/public/js/cockpit.js
git -c user.name="Baro Service" -c user.email="baroservicellc@gmail.com" `
  commit -m "feat(drawer): Customer typeahead with pick / create-new / use-phone affordances"
```

---

### Task 25: Dedup pre-check + banners + force_create_new checkbox

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`

- [ ] **Step 1: Replace `triggerPhoneDedupCheck` stub**

```javascript
  let dedupCheckTimer = null;
  function triggerPhoneDedupCheck() {
    clearTimeout(dedupCheckTimer);
    dedupCheckTimer = setTimeout(() => doPhoneDedupCheck(), 400);
  }

  async function doPhoneDedupCheck() {
    if (!state.createOpen) return;
    const d = state.createDraft || {};
    const phone = (d.caller_phone || '').trim();
    if (!phone && !d.customer_id) {
      state.createDedupWarnings = null;
      renderDedupBanners();
      updateSubmitEnabled();
      return;
    }

    try {
      const r = await call('baro_crm.api.repair_job.find_dedup_warnings', {
        customer: d.customer_id || null,
        customer_name: d.customer_name || null,
        caller_phone: phone || null,
        equipment_type: d.equipment_type || null,
        lookback_days: 90,
      });
      state.createDedupWarnings = r;
      renderDedupBanners();
      updateSubmitEnabled();
    } catch (e) {
      console.error('find_dedup_warnings failed', e);
    }
  }

  function renderDedupBanners() {
    const host = $('#dedupBanners');
    if (!host) return;
    const w = state.createDedupWarnings;
    if (!w) { host.innerHTML = ''; return; }

    const parts = [];

    // Phone multi-match — BLOCKING
    if (w.phone_multi_match && w.phone_multi_match.length > 1) {
      const list = w.phone_multi_match.map(c => `
        <button type="button" class="btn-mini" data-pick-customer="${escapeHtml(c)}">${escapeHtml(c)}</button>
      `).join(' ');
      parts.push(`
        <div class="dedup-banner block">
          <strong>Phone matches ${w.phone_multi_match.length} customers.</strong>
          Pick one or tick "Create new anyway" to proceed with a new Customer.
          <div class="actions">${list}</div>
          <label class="force-create-new-row">
            <input type="checkbox" id="cr_force_new" ${state.createForceNew ? 'checked' : ''}>
            Create new Customer anyway
          </label>
        </div>
      `);
    }

    // Phone single match — informational
    if (w.phone_match_customer) {
      parts.push(`
        <div class="dedup-banner info">
          Phone matches existing Customer <strong>${escapeHtml(w.phone_match_customer)}</strong> —
          will be linked unless you pick a different Customer.
        </div>
      `);
    }

    // Similar customers — soft warn
    if (w.similar_customers && w.similar_customers.length) {
      const list = w.similar_customers.map(s =>
        `<button type="button" class="btn-mini" data-pick-customer="${escapeHtml(s.name)}">${escapeHtml(s.customer_name)}</button>`
      ).join(' ');
      parts.push(`
        <div class="dedup-banner warn">
          Similar existing customers — verify this isn't a duplicate:
          <div class="actions">${list}</div>
        </div>
      `);
    }

    // Active jobs — soft warn
    if (w.active_jobs && w.active_jobs.length) {
      const list = w.active_jobs.slice(0, 3).map(rj => `
        <div class="actions">
          <strong>${escapeHtml(rj.name)}</strong> · ${escapeHtml(rj.equipment_type || '—')} · ${escapeHtml(rj.reason || '')}
          <button type="button" class="btn-mini" data-open-rj="${escapeHtml(rj.name)}">Open RJ</button>
        </div>
      `).join('');
      parts.push(`
        <div class="dedup-banner warn">
          <strong>Possible existing active job(s):</strong>
          ${list}
        </div>
      `);
    }

    host.innerHTML = parts.join('');

    // Wire banner buttons
    host.querySelectorAll('[data-pick-customer]').forEach(el => {
      el.addEventListener('click', () => {
        state.createDraft.customer_id = el.dataset.pickCustomer;
        state.createDraft.customer_name = el.dataset.pickCustomer;
        state.createForceNew = false;
        renderCreateForm();
        renderDedupBanners();
        updateSubmitEnabled();
      });
    });
    host.querySelectorAll('[data-open-rj]').forEach(el => {
      el.addEventListener('click', () => {
        const id = el.dataset.openRj;
        closeCreateDrawer({ force: true });
        openInspector(id);
      });
    });
    const fcn = $('#cr_force_new');
    if (fcn) fcn.addEventListener('change', () => {
      state.createForceNew = fcn.checked;
      state.createDraft.force_create_new = fcn.checked;
      updateSubmitEnabled();
    });
  }
```

- [ ] **Step 2: Commit**

```powershell
git add baro_crm/baro_crm/public/js/cockpit.js
git -c user.name="Baro Service" -c user.email="baroservicellc@gmail.com" `
  commit -m "feat(drawer): dedup pre-check + 4 banner kinds (multi-match blocking, single info, similar warn, active-jobs warn)"
```

---

### Task 26: Submit + surgical insert + open inspector after create

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`

- [ ] **Step 1: Wire submit button**

In `bindEvents`, inside the delegated click handler:

```javascript
    if (e.target.closest('#btnCreateSubmit')) {
      submitCreateRepairJob();
      return;
    }
```

- [ ] **Step 2: Add the submit + insert logic**

Append to section 18:

```javascript
  async function submitCreateRepairJob() {
    if (state.createSubmitting) return;
    const d = state.createDraft || {};

    // Client-side validation — required fields
    const required = ['caller_phone', 'service_state', 'equipment_type', 'symptom', 'urgency'];
    const customerOk = !!(d.customer_id || (d.customer_name && d.customer_name.trim()));
    let firstInvalid = null;

    if (!customerOk) {
      const row = $('#createRepairJobForm [data-field="customer"]');
      if (row) row.classList.add('invalid');
      const err = $('#err_customer');
      if (err) err.style.display = '';
      firstInvalid = firstInvalid || (row && row.querySelector('input,textarea,select'));
    }
    for (const k of required) {
      const val = (d[k] || '').toString().trim();
      if (!val) {
        const row = $(`#createRepairJobForm [data-field="${k}"]`);
        if (row) row.classList.add('invalid');
        const err = $(`#err_${k}`);
        if (err) err.style.display = '';
        firstInvalid = firstInvalid || (row && row.querySelector('input,textarea,select'));
      }
    }
    if (firstInvalid) {
      firstInvalid.focus();
      return;
    }

    // Build payload (omit empty strings; pass force_create_new if set)
    const payload = {};
    for (const k of ['customer_id', 'customer_name', 'caller_phone', 'business_phone_did',
                     'area', 'service_state', 'marketing_source', 'service_address',
                     'equipment_type', 'symptom', 'urgency', 'internal_comment']) {
      if (d[k] && d[k].toString().trim()) payload[k] = d[k].toString().trim();
    }
    if (state.createForceNew) payload.force_create_new = true;

    state.createSubmitting = true;
    const btn = $('#btnCreateSubmit');
    btn.disabled = true;
    btn.textContent = 'Creating…';

    try {
      const r = await call('baro_crm.api.repair_job.create_repair_job', { payload });
      // Success — surgical insert + open inspector
      const newJob = r.doc;
      state.jobs.unshift(newJob);
      state.jobsById[newJob.name] = newJob;
      // Bump totals optimistically
      if (state.totalJobs != null) state.totalJobs += 1;
      // Re-render the affected view surgically
      if (state.activeView === 'list') {
        const tbody = $('#tableBody');
        if (tbody) tbody.insertAdjacentHTML('afterbegin', renderRow(newJob));
      } else if (state.activeView === 'kanban') {
        // Find the column body for this status and prepend the card
        const colTitle = colTitleForStatus(newJob.status);
        if (colTitle) {
          const body = document.querySelector(`.kanban-col-body[data-column="${escapeAttr(colTitle)}"]`);
          if (body) body.insertAdjacentHTML('afterbegin', kanbanCardHtml(newJob));
        }
      }

      // Refresh state counts to keep the tabs honest (cheap, fire-and-forget)
      api.stateCounts().then(c => { state.stateCounts = c; renderStateTabs(); }).catch(() => {});

      // Toast with warnings
      const warningSummary = (r.warnings || []).map(w => w.message).filter(Boolean).join(' · ');
      toast(`Created ${r.name}${warningSummary ? ' · ' + warningSummary : ''}`, 'ok');

      closeCreateDrawer({ force: true });
      openInspector(r.name);
    } catch (e) {
      console.error('create_repair_job failed', e);
      const msg = extractError(e);
      // If it's the multi-match block, surface in dedup-banner host AND toast
      const host = $('#dedupBanners');
      if (host && msg.toLowerCase().includes('matches') && msg.toLowerCase().includes('customers')) {
        host.insertAdjacentHTML('afterbegin',
          `<div class="dedup-banner block"><strong>Cannot create.</strong> ${escapeHtml(msg)}</div>`);
      }
      toast('Create failed: ' + msg, 'err');
    } finally {
      state.createSubmitting = false;
      btn.disabled = false;
      btn.textContent = 'Create Repair Job';
      updateSubmitEnabled();
    }
  }

  function colTitleForStatus(status) {
    for (const [title, set] of Object.entries({
      'Intake':       ['New', 'Need Follow-up'],
      'Sales':        ['Diagnostics Offered', 'Waiting Prepayment', 'Diagnostics Paid', 'Estimate Sent', 'Waiting Client Approval'],
      'Production':   ['Technician Assigned', 'Diagnostics In Progress', 'Diagnosis Completed', 'Parts Needed', 'Repair In Progress', 'Repair Completed'],
      'Money & Care': ['Invoice Sent', 'Paid', 'Warranty Active', 'Closed'],
      'Out':          ['Lost', 'Spam', 'Unrelated'],
    })) {
      if (set.includes(status)) return title;
    }
    return null;
  }

  function escapeAttr(s) {
    return String(s).replace(/"/g, '&quot;');
  }
```

- [ ] **Step 3: Commit**

```powershell
git add baro_crm/baro_crm/public/js/cockpit.js
git -c user.name="Baro Service" -c user.email="baroservicellc@gmail.com" `
  commit -m "feat(drawer): submit with validation + surgical insert + auto-open inspector"
```

---

### Task 27: Empty-table CTA opens drawer

**Files:**
- Modify: `baro_crm/baro_crm/public/js/cockpit.js`

- [ ] **Step 1: Find the empty-table render branch**

In `renderTable`, find the branch that renders when `state.jobs.length === 0`. Replace the empty-state HTML with:

```javascript
      tbody.innerHTML = `<tr><td colspan="9">
        <div class="empty-table">
          <strong>No Repair Jobs in this view</strong>
          ${state.activeState !== 'All'
            ? '<div>Try a different state tab or "All".</div>'
            : '<div>When calls arrive from Zadarma, they will appear here.</div>'}
          <div class="empty-actions">
            <button type="button" class="btn btn-primary" id="btnOpenCreateDrawerFromEmpty">
              + Create Repair Job
            </button>
          </div>
        </div>
      </td></tr>`;
```

- [ ] **Step 2: Wire the click in `bindEvents`**

Add inside the delegated click handler:

```javascript
    if (e.target.closest('#btnOpenCreateDrawerFromEmpty')) {
      openCreateDrawer();
      return;
    }
```

- [ ] **Step 3: Commit**

```powershell
git add baro_crm/baro_crm/public/js/cockpit.js
git -c user.name="Baro Service" -c user.email="baroservicellc@gmail.com" `
  commit -m "feat(drawer): empty-table state shows + Create CTA opening the drawer"
```

---

### Task 28: ★ CHECKPOINT — full F walkthrough

**Files:** none changed (acceptance).

- [ ] **Step 1: Sync + install**

```powershell
cd "C:\Users\epmek\Documents"
scp -r "Erpnext Baro\baro_crm" admin1@100.127.172.110:/home/admin1/
```

```bash
cd ~/baro_crm
./install.sh
```

- [ ] **Step 2: Re-run backend smoke**

From the workstation:

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
& "C:\Users\epmek\Documents\baro-call-sheet-bot\.venv\Scripts\python.exe" `
  .\scripts\verify_create_repair_job.py --execute
```

Expected: all 6 checks pass (T1-T6).

- [ ] **Step 3: Walk the 20 manual browser tests**

Open `http://100.127.172.110:8080/repair-jobs` on Chrome. Execute every test from spec §11.4 in order:

1. Click `+ New Repair Job` topbar → drawer slides in
2. Open drawer when inspector is open → inspector closes first
3. Type 3+ chars in Customer → typeahead shows
4. Click an existing match → field locks with ×
5. Click × → free-text mode
6. Phone field accepts varied formats
7. Click Create with empty required → red borders + "Required"
8. Fill required + Create → drawer closes, RJ appears, inspector opens
9. Phone matches one Customer + different typed name → linked + warn
10. Phone matches multiple Customers → submit blocked, banner with "Create new anyway"
11. Multi-match resolved by picking one → submit succeeds
12. Multi-match resolved by ticking "Create new anyway" → new Customer
13. Active RJ in same equipment+phone → banner with [Open RJ] [Create anyway]
14. Click Open RJ → drawer closes, inspector opens for existing
15. Click Create anyway → banner dismisses, new RJ created
16. Complete address → Address doc created
17. Incomplete address → service_address_text + needs_review=1
18. Esc with dirty fields → confirm "Discard?"
19. Empty filter view → "+ Create Repair Job" CTA in empty state
20. Status pill click in LIST view → popover → pick action → status changes (regression for Bug 1.1)

For each fail: note the symptom + console + network traceback. Fix, commit, re-deploy, re-test only the failed one.

- [ ] **Step 4: ★ Wait for user**

Tell the user: *"Phase D complete. All 6 backend smoke checks + 20 manual browser tests pass [or: tests X, Y failed — see notes]. OK to do Phase E (final commit + roadmap update)?"*

---

## Phase E — Sign-off

### Task 29: Final commit — spec, roadmap, tag

**Files:**
- Modify: `docs/superpowers/specs/2026-05-21-create-repair-job-drawer-design.md`
- Modify: `docs/superpowers/specs/2026-05-19-baro-crm-roadmap.md`
- Modify: `C:\Users\epmek\Documents\obsidian\00_Index.md\ERPNext\Roadmap.md`

- [ ] **Step 1: Update the spec status line**

In `docs/superpowers/specs/2026-05-21-create-repair-job-drawer-design.md`, find:
```
Status: Pending user review.
```
Replace with:
```
Status: Shipped 2026-05-XX. All 6 backend smoke + 20 desktop manual tests passed.
```
(Replace `XX` with actual ship date.)

- [ ] **Step 2: Update both roadmap files**

In `docs/superpowers/specs/2026-05-19-baro-crm-roadmap.md`, find the F row in the revision-2026-05-21 table. Replace `in flight (mid-brainstorm 2026-05-21)` with `✓ Shipped 2026-05-XX`.

In `C:\Users\epmek\Documents\obsidian\00_Index.md\ERPNext\Roadmap.md`, find the F row. Replace its Status cell with `✓ Shipped 2026-05-XX`. J becomes next-up.

- [ ] **Step 3: Tag and push**

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
git add docs/superpowers/specs/2026-05-21-create-repair-job-drawer-design.md `
       docs/superpowers/specs/2026-05-19-baro-crm-roadmap.md
git -c user.name="Baro Service" -c user.email="baroservicellc@gmail.com" `
  commit -m "docs(roadmap): mark sub-project F (Create Repair Job drawer) shipped"
git tag create-rj-drawer-shipped
git log --oneline pre-kanban-dnd..create-rj-drawer-shipped | head -50

# Push to GitHub if remote exists
git push origin main 2>$null
git push origin --tags 2>$null
```

- [ ] **Step 4: Done**

Tell the user: *"F shipped. Tag `create-rj-drawer-shipped` pushed. Next up: J — ERPNext workspace integration."*

---

## Appendix A — Quick recovery commands

| Problem | Recovery |
|---|---|
| Drawer 500 on POST | `tail -80 /home/frappe/frappe-bench/sites/frontend/logs/web.error.log` inside the container |
| `"Cannot select a Group type Customer Group"` | Verify `_get_default_customer_group()` is finding a non-group; `bench --site frontend execute "frappe.db.sql_list('SELECT name FROM \`tabCustomer Group\` WHERE is_group=0')"` |
| Drawer renders but submit fails silently | Open devtools console; `extractError` should now decode `_server_messages` — read the exact message |
| Smoke leaves test records | `python scripts/verify_create_repair_job.py --execute --clean-stale --stale-hours 0` does a full sweep |
| Synthetic seed didn't clean | `BARO_ALLOW_SYNTHETIC=1 python scripts/seed_synthetic_jobs.py --cleanup --execute` |

---

## Appendix B — Self-review checklist after each commit

- ☐ No console errors during testing
- ☐ Only the intended files committed
- ☐ Commit message in conventional-commits style
- ☐ install.sh re-run after backend-affecting change
- ☐ Smoke or browser test for this task passed
