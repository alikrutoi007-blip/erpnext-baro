"""
Install / migrate hooks for baro_crm.

Runs idempotently on every `bench migrate` so that:
  * The Baro Dispatcher role exists (also shipped via the Role fixture as a
    belt-and-braces measure).
  * Baro Dispatcher has the minimum DocType permissions needed to drive the
    /repair-jobs cockpit end-to-end — create / read / write Repair Job AND
    the dependent Customer / Contact / Address records the drawer touches.

Permissions are written as Custom DocPerm rows. Custom DocPerm survives
bench migrate cleanly and never collides with a DocType's built-in `permissions`
table. If you want a Baro Dispatcher to also gain stock ERPNext perms (e.g.
Sales User), add that role on the User document — these perms are additive.
"""

import frappe


DISPATCHER_ROLE = "Baro Dispatcher"

# DocType -> action flags to grant. Keep this list short and explicit;
# anything missing here means "not granted by baro_crm".
DISPATCHER_PERMS = {
    "Repair Job": {
        "read": 1, "create": 1, "write": 1,
        "email": 1, "print": 1, "report": 1, "share": 1,
        # explicit deny — Frappe defaults each to 0 anyway, included for clarity
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


def after_install():
    """Called once when `bench install-app baro_crm` runs."""
    ensure_dispatcher_role()
    ensure_dispatcher_perms()


def after_migrate():
    """Called on every `bench migrate`. Idempotent."""
    ensure_dispatcher_role()
    ensure_dispatcher_perms()


def ensure_dispatcher_role():
    """The Role fixture should already place this row; this is a safety net
    for the case where fixtures haven't loaded yet on a fresh install."""
    if frappe.db.exists("Role", DISPATCHER_ROLE):
        return
    role = frappe.new_doc("Role")
    role.update({
        "role_name": DISPATCHER_ROLE,
        "desk_access": 1,
        "is_custom": 1,
        "module": "Baro CRM",
        "disabled": 0,
    })
    role.insert(ignore_permissions=True)


def ensure_dispatcher_perms():
    if not frappe.db.exists("Role", DISPATCHER_ROLE):
        # Created next migrate when the fixture loads.
        return

    changed = False
    for doctype, perms in DISPATCHER_PERMS.items():
        if not frappe.db.exists("DocType", doctype):
            # Skip e.g. on a partial install where ERPNext isn't there yet.
            continue
        existing = frappe.db.exists("Custom DocPerm", {
            "parent": doctype,
            "role": DISPATCHER_ROLE,
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
            "role": DISPATCHER_ROLE,
            "permlevel": 0,
            **perms,
        })
        cp.insert(ignore_permissions=True)
        changed = True

    if changed:
        frappe.db.commit()
        frappe.clear_cache()
