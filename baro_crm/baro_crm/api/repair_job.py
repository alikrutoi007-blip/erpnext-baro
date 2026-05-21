"""
Whitelisted REST endpoints consumed by the Repair Jobs cockpit (/repair-jobs).

All methods enforce Frappe permissions via has_permission() or by going through
frappe.get_doc / doc.save which Frappe permission-checks server-side. Every
write also goes through doc.save() so the Version log (timeline) captures the
field change automatically — `Repair Job` has track_changes: 1.

Reachable from JS as:
    frappe.call({ method: 'baro_crm.api.repair_job.get_jobs', args: {...} })
"""

import frappe
from frappe import _


# Repair Job fields the cockpit list view needs. Keep this list tight so the
# get_jobs response stays small on big sites.
LIST_FIELDS = [
    "name",
    "customer",
    "status",
    "caller_phone",
    "business_phone_did",
    "area",
    "service_state",
    "marketing_source",
    "equipment_type",
    "equipment_brand",
    "equipment_model",
    "symptom",
    "urgency",
    "technician",
    "assigned_dispatcher",
    "estimate_manager",
    "production_manager",
    "call_datetime",
    "call_duration_seconds",
    "ai_call_summary",
    "purpose_of_call",
    "diagnostic_price",
    "prepayment_status",
    "estimate_amount",
    "client_approval_status",
    "parts_needed",
    "parts_status",
    "next_follow_up_datetime",
    "modified",
    "owner",
]


# Defense-in-depth allowlist for inline-edit. `status` is intentionally NOT here —
# it must go through the workflow via change_status() so transitions are role-
# checked and the action shows up in the workflow log.
EDITABLE_FIELDS = {
    "customer",
    "contact",
    "service_address",
    "caller_phone",
    "business_phone_did",
    "area",
    "service_state",
    "marketing_source",
    "equipment_type",
    "equipment_brand",
    "equipment_model",
    "symptom",
    "urgency",
    "diagnostic_price",
    "prepayment_status",
    "assigned_dispatcher",
    "estimate_manager",
    "production_manager",
    "technician",
    "mentor",
    "diagnosis_result",
    "estimate_amount",
    "client_approval_status",
    "parts_needed",
    "parts_status",
    "repair_result",
    "warranty_start_date",
    "warranty_end_date",
    "next_follow_up_datetime",
    "internal_comment",
}


STATES = ["Texas", "Florida", "New York", "New Jersey"]


# -----------------------------------------------------------------------------
# F helpers — safe defaults, phone normalization, address parsing, dedup
# -----------------------------------------------------------------------------

def _required_repair_job_defaults(payload):
    """Backfill mandatory legacy fields that the minimal cockpit drawer hides."""
    state = (payload.get('service_state') or '').strip()
    equipment = (payload.get('equipment_type') or '').strip()
    symptom = (payload.get('symptom') or '').strip()
    urgency = (payload.get('urgency') or '').strip()

    area = (
        (payload.get('area') or '').strip()
        or (payload.get('city_area') or '').strip()
        or (f"USA, {state}" if state else "USA")
    )
    purpose = (
        (payload.get('purpose_of_call') or '').strip()
        or symptom
        or f"{equipment} service request".strip()
    )
    summary_bits = [bit for bit in (urgency, equipment, symptom) if bit]
    service_summary = (
        (payload.get('service_summary') or '').strip()
        or " - ".join(summary_bits)
        or "Repair service request"
    )
    return area, purpose, service_summary

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
        frappe.throw(_('No non-group Customer Group exists. Create one in Setup -> Customer Group.'))
    return rows[0]


def _get_default_territory():
    """Non-group Territory. Prefer 'Commercial'. Throws if no non-group exists."""
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
    """Always returns +<digits> or ''. Never returns the raw string.

    Examples:
        '+1 (212) 555-0101' -> '+12125550101'
        '212-555-0101'      -> '+12125550101'
        '+44 20 7946 0958'  -> '+442079460958'
        ''                  -> ''
    """
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


def _find_customers_by_phone(phone_norm):
    """Set of distinct Customer IDs reachable from this phone.
    Sources: Contact.mobile_no, Contact.phone, Repair Job.caller_phone,
    Customer.normalized_phone (when sub-project K's migration adds the column).
    """
    if not phone_norm:
        return set()
    cust_ids = set()

    # (1) Contact.mobile_no / Contact.phone -> Dynamic Link -> Customer
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

    # (2) Existing Repair Job caller_phone -> its Customer
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


def _ensure_customer_contact(customer_id, phone_norm, first_name=None):
    """Idempotent. Ensures the Customer has a Contact carrying this phone.
    Strengthens future phone-based dedup. Returns the Contact name (existing or new)."""
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


def _resolve_customer(payload, warnings):
    """Strict priority - no silent fuzzy-link. See spec section 8.2."""
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
        'message': "Address looks incomplete - stored as raw text on the job. Review and create a proper Address later.",
    })
    return None, raw, 1


# -----------------------------------------------------------------------------
# Read endpoints
# -----------------------------------------------------------------------------

def _initials(name):
    parts = (name or "").split()
    if not parts:
        return "U"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


@frappe.whitelist()
def get_boot_context():
    """Runtime context for /repair-jobs; avoids relying on page Jinja meta."""
    if frappe.session.user in ("Guest", None, ""):
        frappe.throw(_("Login required"), frappe.PermissionError)

    user_doc = frappe.db.get_value(
        "User",
        frappe.session.user,
        ["full_name", "user_image", "username"],
        as_dict=True,
    ) or {}
    full_name = user_doc.get("full_name") or frappe.session.user
    company = frappe.db.get_single_value("Global Defaults", "default_company") or "Baro Service LLC"
    return {
        "user": frappe.session.user,
        "user_full_name": full_name,
        "user_initials": _initials(full_name),
        "user_image": user_doc.get("user_image") or "",
        "company": company,
        "can_write_repair_job": 1 if frappe.has_permission("Repair Job", "write") else 0,
        "can_read_repair_job": 1 if frappe.has_permission("Repair Job", "read") else 0,
    }


TERMINAL_STATUSES = ["Closed", "Lost", "Spam", "Unrelated"]

# Whitelist of sort modes → real SQL order_by clauses.
# Keep this strict so callers cannot inject arbitrary SQL through sort_by.
SORT_MODES = {
    "modified_desc":      "modified desc",
    "call_datetime_desc": "call_datetime desc",
    "creation_desc":      "creation desc",
    "next_follow_up_asc": "next_follow_up_datetime asc",
    "urgency":            ("FIELD(urgency, 'Emergency','Today','This Week','Scheduled','Unknown'), "
                           "modified desc"),
    "oldest_stuck":       "modified asc",
}


@frappe.whitelist()
def get_jobs(state=None, status=None, search=None,
             limit=500, offset=0, date_from=None, scope="active", city=None,
             sort_by="modified_desc"):
    """Paginated list. Returns {jobs, offset, limit, total?, has_more}.
    total is None when search is active (frappe.db.count doesn't honor or_filters).
    scope: 'active' (default) excludes terminal statuses; 'all' includes them."""
    try:
        limit = max(1, min(int(limit), 2000))
    except (TypeError, ValueError):
        limit = 500
    try:
        offset = max(0, int(offset))
    except (TypeError, ValueError):
        offset = 0

    filters = []
    if state and state != "All":
        filters.append(["service_state", "=", state])
    if status:
        filters.append(["status", "=", status])
    if date_from:
        filters.append(["call_datetime", ">=", date_from])
    if city:
        filters.append(["area", "=", city])
    if scope == "active" and not status:
        filters.append(["status", "not in", TERMINAL_STATUSES])

    or_filters = None
    if search:
        s = f"%{search}%"
        or_filters = [
            ["customer", "like", s],
            ["caller_phone", "like", s],
            ["area", "like", s],
            ["equipment_type", "like", s],
            ["equipment_brand", "like", s],
            ["name", "like", s],
        ]

    order_by = SORT_MODES.get(sort_by, SORT_MODES["modified_desc"])
    rows = frappe.get_list(
        "Repair Job",
        fields=LIST_FIELDS + ["service_address_text", "address_needs_review"],
        filters=filters,
        or_filters=or_filters,
        order_by=order_by,
        limit_start=offset,
        limit_page_length=limit,
    )

    result = {"jobs": rows, "offset": offset, "limit": limit}
    if or_filters:
        # frappe.db.count doesn't honor or_filters - return cheap proxy
        result["has_more"] = len(rows) == limit
        result["total"] = None
    else:
        total = frappe.db.count("Repair Job", filters=filters)
        result["total"] = total
        result["has_more"] = (offset + len(rows)) < total
    return result


@frappe.whitelist()
def get_filter_options():
    """Lightweight payload for the cockpit filter chips: distinct cities (area)
    and any other future option lists. States are static so we don't ship them."""
    rows = frappe.db.sql(
        """SELECT DISTINCT area FROM `tabRepair Job`
           WHERE area IS NOT NULL AND area != ''
           ORDER BY area ASC LIMIT 200""",
        as_dict=True,
    )
    return {"cities": [r["area"] for r in rows]}


@frappe.whitelist()
def get_state_counts():
    """Counts of Repair Jobs by service_state for the tab strip."""
    counts = {"All": frappe.db.count("Repair Job")}
    for s in STATES:
        counts[s] = frappe.db.count("Repair Job", filters={"service_state": s})
    # bucket for jobs without a state set yet (handy for managers)
    counts["Unassigned"] = frappe.db.count(
        "Repair Job", filters=[["service_state", "in", ["", None]]]
    )
    return counts


@frappe.whitelist()
def get_job(repair_job):
    """Full Repair Job doc as a dict, permission-checked."""
    if not frappe.has_permission("Repair Job", "read", doc=repair_job):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    doc = frappe.get_doc("Repair Job", repair_job).as_dict()
    return doc


@frappe.whitelist()
def get_timeline(repair_job, limit=80):
    """
    Merged timeline: field changes (Version log), comments, and the
    automatically-logged workflow transitions.

    Returns a list of normalized entries sorted by creation desc, ready to
    render in the inspector Timeline tab.
    """
    if not frappe.has_permission("Repair Job", "read", doc=repair_job):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    try:
        limit = max(1, min(int(limit), 200))
    except (TypeError, ValueError):
        limit = 80

    items = []

    # 1. Version log — field changes (track_changes is on for Repair Job)
    versions = frappe.get_all(
        "Version",
        filters={"ref_doctype": "Repair Job", "docname": repair_job},
        fields=["name", "owner", "creation", "data"],
        order_by="creation desc",
        limit_page_length=limit,
    )
    for v in versions:
        try:
            import json
            payload = json.loads(v.data or "{}")
        except Exception:
            payload = {}
        items.append({
            "kind": "change",
            "id": v.name,
            "owner": v.owner,
            "creation": v.creation,
            "changes": payload.get("changed", []),
            "added": payload.get("added", []),
            "removed": payload.get("removed", []),
        })

    # 2. Comments (manual notes, also workflow comments)
    comments = frappe.get_all(
        "Comment",
        filters={
            "reference_doctype": "Repair Job",
            "reference_name": repair_job,
        },
        fields=["name", "owner", "creation", "content", "comment_type", "comment_by"],
        order_by="creation desc",
        limit_page_length=limit,
    )
    for c in comments:
        items.append({
            "kind": "comment" if c.comment_type == "Comment" else "info",
            "id": c.name,
            "owner": c.owner or c.comment_by,
            "creation": c.creation,
            "content": c.content,
            "comment_type": c.comment_type,
        })

    items.sort(key=lambda x: x["creation"], reverse=True)
    return items[:limit]


# -----------------------------------------------------------------------------
# Write endpoints
# -----------------------------------------------------------------------------

@frappe.whitelist()
def create_repair_job(payload):
    """Atomic create: resolves Customer + Contact (non-blocking) + Address + Repair Job.
    Contact creation never blocks RJ creation - on failure the RJ is created with
    contact=None and a 'contact-create-failed' warning is returned."""
    if not frappe.has_permission('Repair Job', 'create'):
        frappe.throw(_('Not permitted to create Repair Job'), frappe.PermissionError)

    import json as _json
    if isinstance(payload, str):
        payload = _json.loads(payload)

    warnings = []

    # Service state validation (defensive - UI should constrain)
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

    # Contact - non-blocking. RJ is created even if Contact fails.
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

    area, purpose_of_call, service_summary = _required_repair_job_defaults(payload)

    # Repair Job
    doc = frappe.get_doc({
        'doctype': 'Repair Job',
        'naming_series': 'RJ-.YYYY.-',
        'status': 'New',
        'customer': customer_id,
        'contact': contact_id,
        'caller_phone': phone_norm,
        'business_phone_did': normalize_phone(payload.get('business_phone_did')),
        'area': area,
        'service_state': state,
        'marketing_source': (payload.get('marketing_source') or '').strip(),
        'service_address': address_id,
        'service_address_text': address_text,
        'address_needs_review': needs_review,
        'equipment_type': payload['equipment_type'].strip(),
        'symptom': payload['symptom'].strip(),
        'purpose_of_call': purpose_of_call,
        'service_summary': service_summary,
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


@frappe.whitelist()
def find_dedup_warnings(customer=None, customer_name=None, caller_phone=None,
                       equipment_type=None, lookback_days=90):
    """Returns dedup hints WITHOUT blocking or linking. Drawer surfaces these
    as informational/blocking banners depending on kind."""
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

    # Name - exact + prefix-similar
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
    try:
        lookback = int(lookback_days)
    except (TypeError, ValueError):
        lookback = 90
    cutoff = (datetime.now() - timedelta(days=lookback)).isoformat()
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


@frappe.whitelist()
def set_field(repair_job, fieldname, value):
    """Inline-edit a single field on a Repair Job.

    Goes through doc.save() so:
      - Frappe validates field type / link target
      - Version log records the change (timeline auto-populates)
      - DocType permission rules are enforced
    """
    if not frappe.has_permission("Repair Job", "write", doc=repair_job):
        frappe.throw(_("Not permitted to edit this Repair Job"), frappe.PermissionError)

    if fieldname not in EDITABLE_FIELDS:
        frappe.throw(_("Field '{0}' is not editable from the cockpit. Status changes must use the workflow.").format(fieldname))

    doc = frappe.get_doc("Repair Job", repair_job)

    # Coerce empty strings to None for clean Frappe semantics
    if value == "":
        value = None

    doc.set(fieldname, value)
    doc.save()
    return {
        "ok": True,
        "fieldname": fieldname,
        "value": doc.get(fieldname),
        "modified": doc.modified,
    }


@frappe.whitelist()
def add_comment(repair_job, content):
    """Add a human-readable comment to a Repair Job. Appears in the timeline."""
    if not frappe.has_permission("Repair Job", "write", doc=repair_job):
        frappe.throw(_("Not permitted to comment on this Repair Job"), frappe.PermissionError)

    content = (content or "").strip()
    if not content:
        frappe.throw(_("Comment cannot be empty"))

    user = frappe.session.user
    full_name = frappe.db.get_value("User", user, "full_name") or user

    comment = frappe.get_doc({
        "doctype": "Comment",
        "comment_type": "Comment",
        "reference_doctype": "Repair Job",
        "reference_name": repair_job,
        "content": content,
        "comment_email": user,
        "comment_by": full_name,
    })
    comment.insert(ignore_permissions=True)
    return {
        "id": comment.name,
        "owner": user,
        "owner_full_name": full_name,
        "creation": comment.creation,
        "content": content,
    }


@frappe.whitelist()
def change_status(repair_job, action):
    """Apply a workflow action — role-checked + logged via Frappe's workflow engine."""
    from frappe.model.workflow import apply_workflow

    if not frappe.has_permission("Repair Job", "write", doc=repair_job):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    doc = frappe.get_doc("Repair Job", repair_job)
    apply_workflow(doc, action)
    return {
        "ok": True,
        "status": doc.status,
        "modified": doc.modified,
    }


# -----------------------------------------------------------------------------
# Lookup helpers used by inline-edit selects (link fields)
# -----------------------------------------------------------------------------

@frappe.whitelist()
def search_link(doctype, query="", limit=10):
    """Lightweight search for link-type inline edits (Customer, Employee, Address...)."""
    allowed = {"Customer", "Contact", "Address", "Employee", "User", "Lead Source"}
    if doctype not in allowed:
        frappe.throw(_("DocType '{0}' is not searchable from the cockpit").format(doctype))

    try:
        limit = max(1, min(int(limit), 25))
    except (TypeError, ValueError):
        limit = 10

    q = f"%{(query or '').strip()}%"
    title_field = {
        "Customer": "customer_name",
        "Contact": "first_name",
        "Address": "address_title",
        "Employee": "employee_name",
        "User": "full_name",
        "Lead Source": "name",
    }.get(doctype, "name")

    rows = frappe.get_list(
        doctype,
        fields=["name", title_field],
        or_filters=[["name", "like", q], [title_field, "like", q]] if query else None,
        order_by="modified desc",
        limit_page_length=limit,
    )
    return [{"value": r["name"], "label": r.get(title_field) or r["name"]} for r in rows]
