# Create Repair Job drawer (in-cockpit) — design

Date: 2026-05-21
Status: Pending user review.
Roadmap parent: `2026-05-19-baro-crm-roadmap.md` (sub-project F, post-2026-05-21 revision)
Implementation target: `baro_crm` Frappe app
Estimated effort: 2–3 days

---

## 1. Goal

Replace the cockpit's "+ New Repair Job" topbar button (which currently links to `/app/repair-job/new`, the stock ERPNext form) with an in-cockpit right-side drawer that creates a Repair Job from a minimal field set, runs dedup pre-checks against existing customers and active jobs, and opens the new RJ in the inspector on success.

The drawer is the first new feature after E (kanban drag/drop) and folds in audit polish that the cockpit needs at production volume: status popover regression fix, focus-trap helper, `extractError` decoding, `kanbanCardHtml`/`renderRow` extraction, `state.jobsById` map, kanban column natural-height with sticky headers, paginated `get_jobs`, and friendlier error toasts.

## 2. Success criteria

F is "done" when all of the following hold:

- The topbar "+ New Repair Job" button opens a right-side drawer (not `/app/repair-job/new`).
- Drawer renders 6 required fields + 4 optional fields per §6.
- Customer typeahead searches existing customers, allows pick-existing OR create-new-on-submit.
- Phone, name, and active-job dedup pre-checks fire and surface as warnings/banners in the drawer; no silent fuzzy linking.
- Phone multi-match **blocks** silent creation: dispatcher must either pick one of the matched customers or explicitly check "Create new anyway".
- Successful create returns the new RJ as a dict, the drawer closes, the inspector opens for the new RJ.
- Surgical post-create insert: the new RJ appears in the active view without a full table/kanban re-render.
- Status popover regression (audit Bug 1.1) is fixed and verified.
- All 20 manual browser tests in §11 pass; all 12/14 E desktop acceptance tests still pass.
- `verify_create_repair_job.py` backend smoke (§11.2) passes against the live ERPNext.

## 3. Constraints (consolidated)

1. **In-cockpit drawer pattern**, mirroring the inspector's shape, animation, and overlay. Mutually exclusive with inspector (opening one closes the other).
2. **No optimistic insert.** Server is the source of truth; drawer holds state until response.
3. **No silent fuzzy linking** for customers. Phone-multi-match refuses silent creation; name-multi-match throws; only explicit typeahead pick OR exact normalized name match OR explicit "Create new anyway" auto-links/creates.
4. **Cautious address handling.** Only create an `Address` doc when text parses into street + city + state (with optional ZIP). Otherwise store raw text on the Repair Job and flag for review. Parser regex in §8.1.
5. **Required-field validation on submit**, with inline progressive error display. No nag-while-typing.
6. **Dedup pre-checks** are warnings only inside F (full attach-to-existing flow is sub-project H). Two endpoints: `find_dedup_warnings` (live during drawer use) and `create_repair_job` (atomic insert with same checks).
7. **Scale handling**: paginated `get_jobs` (500 default, 2000 max, `has_more` honesty during search); kanban columns natural-height with sticky heads; page-level scroll.
8. **Audit polish** folded in per §10. Notably: status popover bug, focus trap helper, `extractError` decoding, surgical render helpers.
9. **No new DocType.** Lead Intake is status-based (sub-project I is folded into G). The "Lead" concept lives in the `New` / `Need Follow-up` statuses; F doesn't change that.
10. **Non-group `Customer Group` and `Territory`.** F's Customer creation must not pick group-type nodes (Frappe blocks this; we've already hit it).

## 4. Architecture and component layout

### 4.1 Component shape

```
.baro-cockpit
├── .sidebar
├── .main
├── .inspector-overlay       ← shared (existing); also used by drawer
├── .inspector               ← existing
└── .create-drawer           ← NEW, same right-side animation as inspector
    ├── .insp-head            (reused chrome class)
    │   ├── title "New Repair Job"
    │   └── close button (X)
    ├── .insp-body
    │   ├── #dedupBanners      (optional, populated by find_dedup_warnings)
    │   ├── form#createRepairJobForm
    │   │   ├── required fields section
    │   │   └── optional fields section (collapsed by default)
    │   └── (no tabs in v1)
    └── .insp-actionbar
        ├── [ Cancel ]
        └── [ Create Repair Job ]
```

Mutual exclusion: opening the drawer triggers `closeInspector()`; opening the inspector triggers `closeCreateDrawer()`.

### 4.2 File changes

| Path | Change | Approx |
|---|---|---|
| `baro_crm/baro_crm/public/js/cockpit.js` | +280 lines new (section 17); ~70 lines refactored | net +220 |
| `baro_crm/baro_crm/public/css/cockpit.css` | +60 lines (drawer + dedup banners) | +60 |
| `baro_crm/baro_crm/api/repair_job.py` | +180 lines (create_repair_job, find_dedup_warnings, helpers, revised get_jobs) | +180 |
| `baro_crm/baro_crm/fixtures/custom_field.json` | +2 fields (service_address_text, address_needs_review) | +2 entries |
| `baro_crm/baro_crm/hooks.py` | extend `fixtures.filters.fieldname.in` list | +2 strings |
| `scripts/verify_create_repair_job.py` | NEW backend smoke script | ~200 lines |
| `scripts/seed_synthetic_jobs.py` | NEW load-test fixture (TEST-F- prefix; cleanup mode) | ~120 lines |
| `baro_crm/install.sh` | no change |
| `baro_crm/DEPLOY.md` | +20 lines documenting `verify_create_repair_job.py` |

### 4.3 State additions in cockpit.js

```javascript
const state = {
  // ... existing ...
  jobsById: {},                  // NEW — O(1) lookups, rebuilt on every loadAll
  createOpen: false,             // NEW — drawer open
  createDraft: null,             // NEW — form values for current session (for dirty-confirm)
  createDedupWarnings: null,     // NEW — last find_dedup_warnings response
  createForceNew: false,         // NEW — explicit "Create new anyway" flag
  customerLookupCache: new Map(),// NEW — typeahead result cache
  totalJobs: null,               // NEW — for "Load more" footer
  hasMoreJobs: false,            // NEW — same
};
```

`state.jobsById` is rebuilt on every successful `loadAll`. Existing 14 `state.jobs.find(j => j.name === id)` call sites become `state.jobsById[id]`. F adds the 15th. Same data, two indexes.

### 4.4 Data-flow paths

#### 4.4.1 Drawer open

1. User clicks topbar "+ New Repair Job" button.
2. `closeInspector()` if `state.selectedId`.
3. `state.createOpen = true`; `state.createDraft = {}`; `state.createForceNew = false`.
4. Drawer DOM is built (lazy) and appended inside `.baro-cockpit`.
5. Focus moves to Customer input. Focus trap installed.
6. Topbar button enters disabled visual state.

#### 4.4.2 Customer typeahead

1. User types ≥2 chars in Customer field.
2. Debounced 200ms; query hits `baro_crm.api.repair_job.search_link` (existing) for `Customer`.
3. Results cached in `state.customerLookupCache` per query string.
4. Up to 8 results render below the input, sorted by `modified desc`. Three system rows append:
   - "+ Create new '{typed}'" (greyed unless ≥3 chars)
   - "Use phone +X — no name" (shown only when Caller Phone non-empty)
   - "Create new anyway" (shown only when `find_dedup_warnings.phone_match_customer === 'multi-match'`)
5. ↑↓ navigate, Enter selects, Esc closes panel without selection.
6. Click an existing match → `state.createDraft.customer_id = <id>`, input shows the picked name, locked with × to release.
7. Click "+ Create new" → input stays as free text, no `customer_id`.
8. Click "Use phone" → input cleared, no `customer_id`.

#### 4.4.3 Dedup pre-check (`find_dedup_warnings`)

Triggered:
- After Customer picked from typeahead (with phone)
- After Caller Phone field blurs (debounced 400ms)
- On submit (last-chance check)

Backend returns `{phone_match_customer, name_match_customer, similar_customers, active_jobs, phone_multi_match}`. Drawer renders banners (yellow, dismissible per-banner):

- **Phone matches one Customer** + typed name differs → "Phone +X belongs to '{Customer}'. Linked to that customer."
- **Phone matches multiple Customers** → red panel listing each as a clickable card. Submit is **blocked** until dispatcher either picks one (→ sets `customer_id`) or explicitly checks the "Create new anyway" checkbox (→ sets `state.createForceNew = true`).
- **Name has similar existing customers** → grey info: "Similar existing: 'Marriott Hotel'. Verify this isn't a duplicate." Submit not blocked.
- **Active job exists** → orange banner: "Possible existing active job: RJ-NNNN — Customer • equipment • N days ago. [Open RJ] [Create anyway]". Buttons: "Open RJ" closes drawer and opens inspector for that RJ; "Create anyway" dismisses the banner. Submit not blocked by this banner.

#### 4.4.4 Submit (happy path, no multi-match)

1. Client validates 6 required fields filled. If missing: red borders + "Required" + focus on first invalid; button stays enabled; no API call.
2. Client builds payload: `{customer_id?, customer_name, caller_phone, business_phone_did?, area?, service_state, marketing_source?, service_address?, equipment_type, symptom, urgency, internal_comment?, force_create_new?}`.
3. Button shows spinner + "Creating…"; disabled.
4. `POST /api/method/baro_crm.api.repair_job.create_repair_job` with payload.
5. Server resolves Customer → Contact → Address → Repair Job (see §8). Returns `{ok: true, name, doc, warnings}`.
6. Client:
   - `state.jobs.unshift(doc); state.jobsById[doc.name] = doc;`
   - If list view active: `tableBody.insertAdjacentHTML('afterbegin', renderRow(doc))`
   - If kanban view active: `colBody[doc.status].insertAdjacentHTML('afterbegin', kanbanCardHtml(doc))`
   - Refresh state counts: `api.stateCounts().then(c => { state.stateCounts = c; renderStateTabs(); })`
   - `closeCreateDrawer()`
   - `openInspector(doc.name)`
   - Toast: `Created RJ-NNNN.` + any warnings appended (e.g., "Created new Customer 'X'.")

#### 4.4.5 Submit (multi-match phone, no `force_create_new`)

1–4 same as happy path. Server throws `frappe.throw('Phone +X matches N customers. Pick one or check Create new anyway.')`.
5. Client catches; `extractError` (now decoding `_server_messages` properly) returns the friendly string.
6. Red drawer-top banner: the message + a link to the dedup panel above.
7. Submit button re-enables.
8. Dispatcher resolves by picking a customer OR ticking the new "Create new anyway" checkbox in the dedup panel; resubmits.

#### 4.4.6 Submit (server validation error)

1–4 same. Server throws specific field error (e.g., `Symptom is required`).
5. Client maps the error to the field if `_server_messages.field` is present; otherwise drawer-top banner.
6. Button re-enables.

#### 4.4.7 Drawer close with dirty fields

1. User hits Esc / Cancel / clicks overlay.
2. If `createDirty()` (any field non-default): confirm modal "Discard new Repair Job? Customer 'X' and N other fields will be lost. [Cancel] [Discard]". Default focus Cancel.
3. Confirm → `closeCreateDrawer()`. Cancel → stay in drawer.

If empty fields: close immediately without confirm.

## 5. Drop-in Customer typeahead UX

```
┌─ Customer * ─────────────────────────────────────┐
│ marrio_                                          │ ← input
└─ panel ─────────────────────────────────────────┘
  ▸ Marriott Residence Inn       NYC   ← existing
  ▸ Marriott Marquis             NYC   ← existing
  ▸ Marriott Bonvoy Cafe         Boston ← existing
  ─────────────────────────────────────
  + Create new "marrio_"                  (≥3 chars)
  + Use phone +12125550101                 (when phone filled)
```

## 6. Field scope (minimal)

### 6.1 Required (6)

| Field | Type | Default | Notes |
|---|---|---|---|
| Customer | text + typeahead | — | See §5. Resolves to `customer_id` if picked, else `customer_name` for new |
| Caller Phone | text | — | Free format; normalized on submit |
| Service State | select | — | Texas / Florida / New York / New Jersey |
| Equipment Type | text | — | Free text in v1 (Item Group link is sub-project G) |
| Symptom | textarea | — | 2-3 lines |
| Urgency | select | — | Emergency / Today / This Week / Scheduled / Unknown |

### 6.2 Optional (4, collapsed)

| Field | Type | Notes |
|---|---|---|
| Business Phone (DID) | text | The Baro DID the call came in on |
| Marketing Source | text | "BaroSite NY", "Google Ads", etc. — free text in v1 |
| Service Address | textarea | See §8.3 for cautious handling |
| Internal Comment | textarea | Dispatcher notes |

Status defaults to `New`. All other fields (assignment, diagnostic price, AI summary, transcript, etc.) are filled later via the inspector.

## 7. Scale handling

### 7.1 Pagination

Default `get_jobs` returns 500 jobs sorted `modified desc`, with `has_more` flag. "Load 500 more" button at the bottom of the active view (list or kanban) appends to state on click. Max-per-page server-side is 2000.

`get_jobs` response shape:
```json
{
  "jobs": [...],
  "offset": 0,
  "limit": 500,
  "total": 4823,    // null when search is active (or_filters), see §8.4
  "has_more": true
}
```

### 7.2 Kanban columns natural-height

CSS changes:
```css
.baro-cockpit .kanban-col       { /* remove max-height */ }
.baro-cockpit .kanban-col-body  { /* remove overflow-y: auto */ }
.baro-cockpit .kanban-wrap      { overflow-x: auto; overflow-y: visible; }
.baro-cockpit .kanban-col-head  { position: sticky; top: 0;
                                  background: var(--surface-2); z-index: 2; }
```

Result: columns grow to fit cards, whole page scrolls vertically, column heads stay pinned as user scrolls inside a tall column. Empty bottom space next to tall columns is acceptable (matches Trello/Linear at scale).

### 7.3 Performance

- `state.jobsById` map rebuilt on every `loadAll`. Eliminates 14 `Array.find` call sites.
- `kanbanCardHtml(j)` and `renderRow(j)` extracted; F's surgical insert calls them.
- `renderKanban` pre-groups state.jobs by status once: `const byStatus = state.jobs.reduce(...);` then each column does `byStatus[k] || []`. O(N) once instead of O(N·M).
- Surgical post-create insert: no `renderTable()` / `renderKanban()` after one new row.

### 7.4 Network

- `loadAll` carries a request token; new call cancels previous response handler.
- Customer typeahead: 200ms debounce, in-memory cache per query.
- Dedup warnings: 400ms debounce on phone blur.

## 8. Backend API

### 8.1 Helpers

```python
def _get_default_customer_group():
    """Return a non-group Customer Group. Prefer 'Commercial'."""
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


def _find_customers_by_phone(phone_norm):
    """Set of distinct Customer IDs reachable from this phone.
    Sources: Contact.mobile_no, Contact.phone, Repair Job.caller_phone,
    Customer.normalized_phone (when K's migration adds the column).
    """
    if not phone_norm:
        return set()
    cust_ids = set()

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

    rj_customers = frappe.db.sql_list("""
        SELECT DISTINCT customer FROM `tabRepair Job`
        WHERE caller_phone = %s AND customer IS NOT NULL AND customer != ''
    """, (phone_norm,))
    cust_ids.update(rj_customers)

    if frappe.db.has_column('tabCustomer', 'normalized_phone'):
        cust_ids.update(frappe.db.sql_list("""
            SELECT name FROM `tabCustomer` WHERE normalized_phone = %s
        """, (phone_norm,)))

    return cust_ids


def _ensure_customer_contact(customer_id, phone_norm, first_name=None):
    """Idempotent: ensures the Customer has a Contact carrying this phone.
    Strengthens future phone-based dedup."""
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


def _parse_address_text(raw):
    """Conservative. Only 'complete' when street# + city + state present."""
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

### 8.2 `_resolve_customer` — strict priority

```python
def _resolve_customer(payload, warnings):
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

    # 2. Phone match
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
                'customers': list(matches),
                'message': f"Created new Customer despite {len(matches)} phone matches.",
            })
            # fall through to step 3/4

    # 3. Exact name match (case-insensitive, trim only)
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

### 8.3 `_resolve_address` — cautious

```python
def _resolve_address(payload, customer_id, warnings):
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

### 8.4 `create_repair_job` — atomic insert

```python
@frappe.whitelist()
def create_repair_job(payload):
    """Atomic create: resolves Customer + Address + Contact, inserts Repair Job."""
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

    # Customer (no silent fuzzy)
    customer_id = _resolve_customer(payload, warnings)

    # Address (cautious)
    address_id, address_text, needs_review = _resolve_address(payload, customer_id, warnings)

    # Repair Job
    doc = frappe.get_doc({
        'doctype': 'Repair Job',
        'naming_series': 'RJ-.YYYY.-',
        'status': 'New',
        'customer': customer_id,
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

    # Strengthen future dedup
    if phone_norm and customer_id:
        _ensure_customer_contact(customer_id, phone_norm,
                                 first_name=(payload.get('contact_first_name') or None))

    return {
        'ok': True,
        'name': doc.name,
        'doc': doc.as_dict(),
        'warnings': warnings,
    }
```

### 8.5 `find_dedup_warnings` — non-blocking pre-check

```python
@frappe.whitelist()
def find_dedup_warnings(customer=None, customer_name=None, caller_phone=None,
                       equipment_type=None, lookback_days=90):
    """Non-blocking warnings for the drawer. Mirrors _resolve_customer's checks
    but returns structured info instead of throwing / creating."""
    out = {
        'phone_match_customer': None,    # single match
        'phone_multi_match': [],         # multiple matches — blocks silent create
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

    # Name exact match
    if name_norm:
        rows = frappe.db.sql_list("""
            SELECT name FROM `tabCustomer`
            WHERE LOWER(TRIM(customer_name)) = %s LIMIT 2
        """, (name_norm,))
        if len(rows) == 1:
            out['name_match_customer'] = rows[0]
        # similar (prefix only, ≥3 chars)
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

### 8.6 Revised `get_jobs` — honest pagination

```python
@frappe.whitelist()
def get_jobs(state=None, status=None, search=None,
             limit=500, offset=0, date_from=None):
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

**Client breaking change:** response shape goes from `[...]` to `{jobs, offset, limit, total?, has_more}`. F's `loadAll` rewrite handles both during deploy (graceful degradation removed after migrate succeeds).

### 8.7 New Custom Fields on Repair Job

Append to `baro_crm/baro_crm/fixtures/custom_field.json`:

```json
[
 { /* existing service_state */ },
 {
  "doctype": "Custom Field", "name": "Repair Job-service_address_text",
  "dt": "Repair Job", "fieldname": "service_address_text",
  "label": "Service Address (raw text)", "fieldtype": "Small Text",
  "insert_after": "service_address",
  "description": "Raw text stored when the input couldn't be parsed into a clean Address doc. See address_needs_review.",
  "module": "Baro CRM"
 },
 {
  "doctype": "Custom Field", "name": "Repair Job-address_needs_review",
  "dt": "Repair Job", "fieldname": "address_needs_review",
  "label": "Address needs review", "fieldtype": "Check",
  "insert_after": "service_address_text", "default": "0",
  "description": "Set to 1 when service_address_text is populated but no Address doc was created.",
  "module": "Baro CRM"
 }
]
```

And update `baro_crm/baro_crm/hooks.py`:

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

## 9. Confirmation modal reuse for "Discard new Repair Job?"

The existing `showConfirmDialog` (from E) handles the dirty-close case. Custom title, destructive button reads "Discard". Default focus Cancel.

## 10. Folded-in audit polish

| # | Source | Fix in F | LOC |
|---|---|---|---|
| 1 | Audit 1.1 | Status popover selector → `.pop-item[data-action]:not([data-drag-action])`. Restore real workflow popover. | ~1 |
| 2 | Audit 1.6 | Extract `installFocusTrap(rootEl)`; use in inspector, F drawer, confirm modal. | ~40 |
| 3 | Audit 1.9 | `extractError` decodes `_server_messages` properly; maps `PermissionError`/`TimestampMismatchError` to friendly strings. | ~20 |
| 4 | Audit §4 | Extract `kanbanCardHtml(j)` and `renderRow(j)`. F's surgical insert depends on both. | net +60 |
| 5 | Audit §4 | `state.jobsById` map rebuilt on every loadAll. Replaces 14 `Array.find` calls; F adds the 15th. | ~10 |
| 6 | Audit 1.3 | `handleDragMove` one-line guard: `return !!(evt.to && evt.to.classList.contains('drop-valid'))`. | ~1 |
| 7 | Audit §5 #2 | Empty-table state gets `[+ Create Repair Job]` CTA opening the drawer. | ~10 |
| 8 | Audit §5 #3 | Friendlier error map: PermissionError → "You don't have permission to do that." TimestampMismatchError → "Someone else just updated this. Refresh." | inside #3 |
| 9 | Audit 1.14 | `closeStatusPopover()` restores focus to `state.statusPopoverFor` source element. | ~5 |
| 10 | Audit §3 contrast | `--text-faint`: `#94a3b8` → `#7c8aa1`. 3.0:1 → 4.5:1 on white. | 1 token |
| 11 | Audit §5 #4 | `title="Drag to change status"` on `.kc-handle`. | ~1 |

**Deferred (audit found but not in F):** stale-response race (1.2), empty-column rule cascade (1.5), two `document.click` handlers (1.11), `timelineRefreshTimer` rename (1.13), skeleton screens, full a11y pass (`aria-controls`, `role="option"` on popover items), memoize `colorClass`/`initials`.

## 11. Testing and sign-off

### 11.1 Automated install smoke

Unchanged from E. `install.sh` step 5/6 verifies assets serve through `frontend:8080`.

### 11.2 Backend smoke — `scripts/verify_create_repair_job.py`

New script. Generates a per-run test prefix `TEST-F-YYYYMMDD-<uuid8>` (e.g., `TEST-F-2026-05-21-a1b2c3d4`) and names every record it creates with that prefix. Cleanup deletes by prefix.

```python
#!/usr/bin/env python
"""F backend smoke. Calls create_repair_job + find_dedup_warnings against
the live ERPNext via the existing ERPNextClient. All test records get a
per-run TEST-F-* prefix and are cleaned at the end."""
import argparse, sys, uuid
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from erpnext_client import get_client, ERPNextError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--keep', action='store_true', help='skip cleanup')
    args = parser.parse_args()

    client = get_client()
    if not args.execute and not client.config.dry_run:
        print('Refusing to run write tests without --execute or ERPNEXT_DRY_RUN=1.')
        sys.exit(1)

    run_id = f"TEST-F-{date.today().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
    print(f"Run prefix: {run_id}")

    def call(method, args_=None):
        # Frappe REST whitelisted-method body: args at top level, NOT wrapped in {"args": ...}
        return client._request('POST', f'/api/method/{method}',
                               payload=(args_ or {}))['message']

    failures = []

    def check(name, fn):
        try:
            fn()
            print(f"  OK   {name}")
        except Exception as e:
            failures.append((name, e))
            print(f"  FAIL {name}: {e}")

    # T1: find_dedup_warnings shape
    def t1():
        r = call('baro_crm.api.repair_job.find_dedup_warnings',
                 {'caller_phone': '+12125559999'})
        assert isinstance(r, dict)
        for key in ('phone_match_customer', 'phone_multi_match',
                    'name_match_customer', 'similar_customers', 'active_jobs'):
            assert key in r, f"missing key {key}"
    check('find_dedup_warnings shape', t1)

    # T2: create_repair_job minimal payload
    rj_name = []
    def t2():
        r = call('baro_crm.api.repair_job.create_repair_job', {'payload': {
            'customer_name': f"{run_id} Sunrise Diner",
            'caller_phone': '+12125559001',
            'service_state': 'New York',
            'equipment_type': 'Combi Oven',
            'symptom': 'Not heating',
            'urgency': 'Today',
        }})
        assert r['ok'] is True
        assert r['name'].startswith('RJ-')
        assert r['doc']['naming_series'] == 'RJ-.YYYY.-'
        rj_name.append(r['name'])
    check('create_repair_job minimal payload', t2)

    # T3: active-RJ warning fires on duplicate-ish call
    def t3():
        r = call('baro_crm.api.repair_job.find_dedup_warnings', {
            'caller_phone': '+12125559001',
            'equipment_type': 'Combi Oven',
        })
        assert any(j['name'] == rj_name[0] for j in r['active_jobs']), \
            f"expected RJ {rj_name[0]} in active_jobs, got {r['active_jobs']}"
    check('active-RJ warning fires', t3)

    # T4: incomplete address → service_address_text + needs_review=1
    def t4():
        r = call('baro_crm.api.repair_job.create_repair_job', {'payload': {
            'customer_name': f"{run_id} Vague Address Test",
            'caller_phone': '+12125559002',
            'service_state': 'New York',
            'equipment_type': 'Ice Machine',
            'symptom': 'Stopped making ice',
            'urgency': 'Scheduled',
            'service_address': 'Manhattan',  # incomplete
        }})
        assert r['doc']['service_address'] is None
        assert r['doc']['service_address_text'] == 'Manhattan'
        assert r['doc']['address_needs_review'] == 1
        rj_name.append(r['name'])
    check('incomplete address stored as text', t4)

    # T5: bad customer_id → 404-ish
    def t5():
        try:
            call('baro_crm.api.repair_job.create_repair_job', {'payload': {
                'customer_id': 'NONEXISTENT-CUSTOMER-XYZ',
                'caller_phone': '+12125559003',
                'service_state': 'New York',
                'equipment_type': 'Fryer',
                'symptom': 'Test',
                'urgency': 'Scheduled',
            }})
            raise AssertionError('expected error for bad customer_id')
        except ERPNextError as e:
            assert 'no longer exists' in str(e) or 'does not exist' in str(e)
    check('bad customer_id rejected', t5)

    # T6: phone multi-match refuses without force_create_new, succeeds with it
    def t6():
        test_phone = '+12125559099'   # unique to this run; cleaned up via prefix
        # Set up: two Customers + two Repair Jobs sharing the same caller_phone.
        # _find_customers_by_phone unions Contact.* and Repair Job.caller_phone, so
        # two RJs with the same phone but different Customers produces a multi-match.
        cust1 = call('frappe.client.insert', {'doc': {
            'doctype': 'Customer',
            'customer_name': f"{run_id} MultiMatch A",
            'customer_type': 'Company',
        }})['name']
        cust2 = call('frappe.client.insert', {'doc': {
            'doctype': 'Customer',
            'customer_name': f"{run_id} MultiMatch B",
            'customer_type': 'Company',
        }})['name']
        rj1 = call('baro_crm.api.repair_job.create_repair_job', {'payload': {
            'customer_id': cust1, 'caller_phone': test_phone,
            'service_state': 'New York', 'equipment_type': 'Probe',
            'symptom': 'setup A', 'urgency': 'Scheduled',
        }})['name']
        rj2 = call('baro_crm.api.repair_job.create_repair_job', {'payload': {
            'customer_id': cust2, 'caller_phone': test_phone,
            'service_state': 'New York', 'equipment_type': 'Probe',
            'symptom': 'setup B', 'urgency': 'Scheduled',
        }})['name']
        rj_name.extend([rj1, rj2])

        # Without force_create_new: backend must throw
        try:
            call('baro_crm.api.repair_job.create_repair_job', {'payload': {
                'customer_name': f"{run_id} MultiMatch Blocked",
                'caller_phone': test_phone,
                'service_state': 'New York', 'equipment_type': 'Probe',
                'symptom': 'should be blocked', 'urgency': 'Scheduled',
            }})
            raise AssertionError('expected throw on multi-match without force_create_new')
        except ERPNextError as e:
            assert 'matches' in str(e).lower() or 'ambiguous' in str(e).lower(), \
                f"unexpected error text: {e}"

        # With force_create_new=true: succeeds, warning surfaces
        r = call('baro_crm.api.repair_job.create_repair_job', {'payload': {
            'customer_name': f"{run_id} MultiMatch Forced",
            'caller_phone': test_phone,
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

    # Cleanup
    if not args.keep:
        print("Cleaning up...")
        for name in rj_name:
            try:
                client._request('DELETE',
                                f'/api/resource/Repair Job/{name}')
                print(f"  deleted RJ {name}")
            except Exception as e:
                print(f"  cleanup warn: RJ {name}: {e}")
        # Also delete the Customer records by name prefix
        for cust in client.list_docs('Customer',
                                      filters=[['name', 'like', f'%{run_id}%']],
                                      fields=['name'], limit=50):
            try:
                client._request('DELETE',
                                f'/api/resource/Customer/{cust["name"]}')
                print(f"  deleted Customer {cust['name']}")
            except Exception as e:
                print(f"  cleanup warn: Customer {cust['name']}: {e}")

    if failures:
        print(f"\n{len(failures)} failure(s).")
        sys.exit(1)
    print("\nAll backend smoke checks passed.")
```

Run as `python scripts/verify_create_repair_job.py --execute`. Cleanup is automatic unless `--keep`.

### 11.3 Synthetic load fixture — `scripts/seed_synthetic_jobs.py`

New script for scale testing (manual test 19). Creates N synthetic Repair Jobs distributed across statuses, all with `TEST-F-LOAD-<uuid>` prefix on customer names. `--cleanup` mode deletes them all by prefix.

```python
# Skeleton:
# python scripts/seed_synthetic_jobs.py --count 1000 --execute
# python scripts/seed_synthetic_jobs.py --cleanup --execute
```

Critical: never seeds onto a non-demo site. Refuses unless `BARO_ALLOW_SYNTHETIC=1` is set in env. Documented in script header.

### 11.4 Manual browser acceptance (20 tests on Chrome desktop)

| # | Test | Expected outcome |
|---|---|---|
| 1 | Click "+ New Repair Job" in topbar | Drawer slides in from right; inspector closes if open; Customer input focused |
| 2 | Open drawer while inspector is open | Inspector closes first, then drawer opens |
| 3 | Type 3+ chars in Customer field | Typeahead panel shows up to 8 matches; arrow keys + Enter selects |
| 4 | Click an existing match in typeahead | Field shows name; locked with × |
| 5 | Click × to unlock typeahead pick | Free-text mode again |
| 6 | Phone field accepts varied formats | `+1 (212) 555-0101`, `212-555-0101`, `2125550101` all normalize to `+12125550101` on submit |
| 7 | Click [Create] with required field empty | Red border + "Required" inline; focus moves to first invalid; no API call |
| 8 | Fill all required + click [Create], valid | Spinner; drawer closes; new RJ at top of list/kanban; inspector opens for it |
| 9 | Phone matches one existing Customer + typed name differs | Backend links to existing; toast: "Phone +X belongs to '{Cust}'. Linked." |
| 10 | Phone matches multiple Customers + dispatcher does NOT pick or check "Create new anyway" | Submit blocked with drawer-top banner "Phone matches N customers. Pick one or tick Create new anyway." No RJ created. |
| 11 | Multi-match resolved by picking a Customer from the warning panel | Field shows picked Customer; submit succeeds; RJ linked to picked Customer |
| 12 | Multi-match resolved by checking "Create new anyway" | New Customer created with typed name; RJ links to it; warning "Created new despite N matches" |
| 13 | Active RJ in same customer+equipment within 90 days | Drawer banner: "Possible existing active job: RJ-NNNN — [Open RJ] [Create anyway]" |
| 14 | Click [Open RJ] on active-job banner | Drawer closes; inspector opens for existing RJ; no new RJ |
| 15 | Click [Create anyway] on active-job banner | Banner dismisses; submit proceeds; new RJ created |
| 16 | Complete address ("124 East 50th, New York, NY 10022") | Address doc created; service_address links; address_needs_review=0 |
| 17 | Incomplete address ("Manhattan") | service_address_text stored on RJ; address_needs_review=1; no Address doc |
| 18 | Esc with dirty fields | "Discard?" confirm; default Cancel; selecting Cancel keeps drawer |
| 19 | Empty filter view (no matches) | Empty-state shows "+ Create Repair Job" CTA; clicking opens drawer |
| 20 | Status pill click in LIST view → popover → pick action | Status changes (regression for Bug 1.1) |

### 11.5 Scale acceptance (separate, runs against synthetic seeds only)

| # | Test | Expected outcome |
|---|---|---|
| S1 | Seed 1000 synthetic jobs via `seed_synthetic_jobs.py --count 1000 --execute` (only on demo or `BARO_ALLOW_SYNTHETIC=1` site) | Script reports OK; 1000 RJs visible in cockpit |
| S2 | Switch to Kanban view with 1000 jobs loaded | Columns natural-height; page scrolls vertically; column heads sticky at top of each column while scrolling within |
| S3 | "Load 500 more" button visible at bottom when has_more=true | Click appends 500 more; button hides when all loaded |
| S4 | `cleanup` mode removes all synthetic jobs | All RJs with TEST-F-LOAD-* prefix gone after run |

### 11.6 E regression (mandatory)

- Test #18 (status popover in list view) verifies Bug 1.1 fix.
- **If E is shipped on this branch (it is — `kanban-dnd-shipped` tag exists):** all 12 desktop tests from E's spec §11.2 must still pass.
- If F were ever built on a branch without E (e.g., a hypothetical rollback), drag/drop regression doesn't apply; status-popover regression always does.

### 11.7 Sign-off

F is "done" when:

- `install.sh` automated smoke green (asset materialization + nginx 200s)
- `verify_create_repair_job.py --execute` all 6 backend checks pass
- 20 manual browser tests pass on Chrome desktop
- 4 scale acceptance tests pass with `seed_synthetic_jobs.py`
- 12 E desktop regression tests pass (status popover fix covered by #20)
- 2 new Custom Fields on Repair Job verified after `bench migrate` (existing one-liner)
- Spec status flipped to "Shipped"
- Roadmap entry for F marked ✓; J becomes next-up

## 12. Out-of-scope

Items the user might expect inside F but are intentionally not:

- **Possible Match panel with Attach-to-existing UI** → sub-project H. F shows warnings only.
- **Existing customer migration / `normalized_phone` column on Customer** → sub-project K. `_find_customers_by_phone` is K-aware (guarded `has_column`).
- **City filter chip + 10 named views (My Queue, Active, Production, etc.)** → sub-project G.
- **Customer Chart deep view** at `/customers/<id>` → sub-project B.
- **ERPNext workspace sidebar shortcut + dispatcher default page** → sub-project J.
- **Client Work Group automation** on Diagnostics Paid → sub-project L.
- **Lead Intake as separate DocType** → status-based (sub-project I folded into G).
- **iPad acceptance for the drawer** → user-side after F deploys.
- **Skeleton screens; full a11y pass (aria-controls, role=option); memoize colorClass/initials** → polish PR after F or rolled into G.
- **Equipment Type as Link (Item Group)** → free text in v1. Link comes with G.
- **Date filter chip (180-day default)** → G feature.

## Appendix A — Open implementation notes

- The drawer DOM is built lazily (first open) and re-used. Closing it hides via `display: none` rather than removing — keeps draft state if user re-opens within the session (cleared on full page reload).
- `find_dedup_warnings` is called three times per drawer session typically (after customer pick, after phone blur, on submit). Cache responses keyed by `(phone_norm, customer_id, customer_name)` in `state.createDedupWarnings` to avoid duplicate calls.
- The "Create new anyway" checkbox lives **inside the phone-multi-match warning panel**, not in the main form area, so it's only visible when relevant. Unchecking it after submit failed re-blocks submit until the dispatcher reconsiders.
- `verify_create_repair_job.py` runs against the live site by design — there's no staging. The `TEST-F-` prefix + per-run UUID prevents accidental name collisions; cleanup runs unless `--keep`.
- `seed_synthetic_jobs.py` is intentionally separate from `verify_create_repair_job.py` because synthetic data is for stress testing, not API correctness. They share the prefix convention.
- `state.jobsById` is rebuilt (not patched) on `loadAll` for simplicity. After F's surgical insert, the map gets one new entry; on next `loadAll` it rebuilds from scratch. Acceptable for our scale.
