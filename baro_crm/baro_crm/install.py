"""
Install / migrate hooks for baro_crm.

Runs idempotently on every `bench migrate` so that:
  * Baro Dispatcher + Baro Reader roles exist (also shipped via the Role
    fixture as a belt-and-braces measure).
  * Baro Dispatcher has the minimum DocType permissions to drive the
    /repair-jobs cockpit end-to-end — read/create/write Repair Job AND the
    dependent Customer / Contact / Address records the drawer touches.
  * Baro Reader has read-only access to the same DocTypes (no create, no
    write, no workflow transitions, no cockpit drag/drop edits).
  * Baro Dispatcher is allowed by the active Repair Job workflow states and
    transitions. Frappe Workflow has its own gate on top of DocPerm. Reader
    is intentionally NOT added here — read-only never changes state.

Permissions are written as Custom DocPerm rows. Custom DocPerm survives
bench migrate cleanly and never collides with a DocType's built-in `permissions`
table.

Role assignment policy (per user 2026-05-24):
  - Assign Baro Dispatcher to users who should work with jobs.
  - Assign Baro Reader to users who should only view.
  - Frappe perms are additive: assigning both is equivalent to Dispatcher
    alone; avoid double-assignment unless intentional.
  - Do NOT widen perms to "All" or every Desk User. Positive roles only.
"""

import frappe


DISPATCHER_ROLE = "Baro Dispatcher"
READER_ROLE = "Baro Reader"

# DocType -> action flags. Anything missing here means "not granted by baro_crm".
DISPATCHER_PERMS = {
    "Repair Job": {
        "read": 1, "create": 1, "write": 1,
        "email": 1, "print": 1, "report": 1, "share": 1,
        "delete": 0, "submit": 0, "cancel": 0, "amend": 0,
        "export": 0, "import": 0,
    },
    "Customer": {
        "read": 1, "create": 1, "write": 1,
        "delete": 0, "export": 0, "import": 0,
    },
    "Contact": {
        "read": 1, "create": 1, "write": 1,
        "delete": 0, "export": 0, "import": 0,
    },
    "Address": {
        "read": 1, "create": 1, "write": 1,
        "delete": 0, "export": 0, "import": 0,
    },
}

# Read-only mirror. Print + report explicitly allowed so a Reader can run the
# standard Frappe report views; everything else hard-zero.
READER_PERMS = {
    "Repair Job": {
        "read": 1, "print": 1, "report": 1,
        "create": 0, "write": 0, "delete": 0,
        "submit": 0, "cancel": 0, "amend": 0,
        "email": 0, "share": 0, "export": 0, "import": 0,
    },
    "Customer": {
        "read": 1,
        "create": 0, "write": 0, "delete": 0, "export": 0, "import": 0,
    },
    "Contact": {
        "read": 1,
        "create": 0, "write": 0, "delete": 0, "export": 0, "import": 0,
    },
    "Address": {
        "read": 1,
        "create": 0, "write": 0, "delete": 0, "export": 0, "import": 0,
    },
}

ROLE_SPECS = [
    (DISPATCHER_ROLE, DISPATCHER_PERMS),
    (READER_ROLE, READER_PERMS),
]


def after_install():
    """Called once when `bench install-app baro_crm` runs."""
    _run_all()


def after_migrate():
    """Called on every `bench migrate`. Idempotent."""
    _run_all()


def _run_all():
    for role, _ in ROLE_SPECS:
        ensure_role(role)
    for role, perms in ROLE_SPECS:
        ensure_perms(role, perms)
    # Workflow access: Dispatcher only. Reader is read-only by design.
    ensure_dispatcher_workflow_access()


def ensure_role(role_name):
    """Safety net for fresh installs where fixtures haven't loaded yet."""
    if frappe.db.exists("Role", role_name):
        return
    role = frappe.new_doc("Role")
    role.update({
        "role_name": role_name,
        "desk_access": 1,
        "is_custom": 1,
        "module": "Baro CRM",
        "disabled": 0,
    })
    role.insert(ignore_permissions=True)


def ensure_perms(role_name, perms_by_doctype):
    if not frappe.db.exists("Role", role_name):
        # Will create next migrate when the fixture loads.
        return

    changed = False
    for doctype, perms in perms_by_doctype.items():
        if not frappe.db.exists("DocType", doctype):
            continue
        existing = frappe.db.exists("Custom DocPerm", {
            "parent": doctype,
            "role": role_name,
            "permlevel": 0,
        })
        if existing:
            # Update in place so policy edits in this file propagate on migrate.
            doc = frappe.get_doc("Custom DocPerm", existing)
            dirty = False
            for k, v in perms.items():
                if doc.get(k) != v:
                    doc.set(k, v)
                    dirty = True
            if dirty:
                doc.save(ignore_permissions=True)
                changed = True
            continue

        cp = frappe.new_doc("Custom DocPerm")
        cp.update({
            "parent": doctype,
            "parenttype": "DocType",
            "parentfield": "permissions",
            "role": role_name,
            "permlevel": 0,
            **perms,
        })
        cp.insert(ignore_permissions=True)
        changed = True

    if changed:
        frappe.db.commit()
        frappe.clear_cache()


def ensure_dispatcher_workflow_access():
    """Let Baro Dispatcher operate the Repair Job workflow.

    DocPerm write is not enough when Workflow is active: Frappe also checks
    Workflow Document State.allow_edit and Workflow Transition.allowed. Both
    fields are single-role links, so we add parallel rows for Baro Dispatcher
    instead of mutating the existing role rows. Baro Reader is intentionally
    NOT added here — read-only by design.
    """
    if not frappe.db.exists("Role", DISPATCHER_ROLE):
        return
    if not frappe.db.exists("DocType", "Workflow"):
        return

    workflows = frappe.get_all(
        "Workflow",
        filters={"document_type": "Repair Job", "is_active": 1},
        pluck="name",
    )
    changed = False

    for workflow_name in workflows:
        workflow = frappe.get_doc("Workflow", workflow_name)
        state_changed = _ensure_workflow_state_rows(workflow)
        transition_changed = _ensure_workflow_transition_rows(workflow)
        if state_changed or transition_changed:
            workflow.save(ignore_permissions=True)
            changed = True

    if changed:
        frappe.db.commit()
        frappe.clear_cache(doctype="Repair Job")
        frappe.clear_cache(doctype="Workflow")


def _ensure_workflow_state_rows(workflow):
    existing = {(row.state, row.allow_edit) for row in workflow.states}
    source_by_state = {}
    for row in workflow.states:
        source_by_state.setdefault(row.state, row)

    changed = False
    for state, source in source_by_state.items():
        if (state, DISPATCHER_ROLE) in existing:
            continue
        workflow.append("states", {
            "state": source.state,
            "doc_status": source.doc_status,
            "allow_edit": DISPATCHER_ROLE,
        })
        changed = True
    return changed


def _ensure_workflow_transition_rows(workflow):
    existing = {
        (row.state, row.action, row.next_state, row.allowed)
        for row in workflow.transitions
    }
    source_by_transition = {}
    for row in workflow.transitions:
        key = (row.state, row.action, row.next_state)
        source_by_transition.setdefault(key, row)

    changed = False
    for (state, action, next_state), source in source_by_transition.items():
        if (state, action, next_state, DISPATCHER_ROLE) in existing:
            continue
        workflow.append("transitions", {
            "state": state,
            "action": action,
            "next_state": next_state,
            "allowed": DISPATCHER_ROLE,
            "allow_self_approval": source.get("allow_self_approval") or 1,
        })
        changed = True
    return changed
