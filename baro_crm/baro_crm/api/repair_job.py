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
# Read endpoints
# -----------------------------------------------------------------------------

@frappe.whitelist()
def get_jobs(state=None, status=None, search=None, limit=200):
    """Return Repair Job rows for the cockpit list, filtered server-side."""
    filters = {}
    if state and state != "All":
        filters["service_state"] = state
    if status:
        filters["status"] = status

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

    try:
        limit = max(1, min(int(limit), 500))
    except (TypeError, ValueError):
        limit = 200

    rows = frappe.get_list(
        "Repair Job",
        fields=LIST_FIELDS,
        filters=filters,
        or_filters=or_filters,
        order_by="modified desc",
        limit_page_length=limit,
    )
    return rows


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
