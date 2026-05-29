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
