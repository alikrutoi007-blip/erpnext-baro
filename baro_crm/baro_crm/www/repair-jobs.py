"""
Web controller for the /repair-jobs cockpit page.

Provides:
  - Authentication gate (redirects to /login if anonymous)
  - Permission check (must have Repair Job 'read')
  - Suppression of all Frappe website chrome (header, footer, sidebar,
    breadcrumbs) so the cockpit renders full-screen.
  - User context for the topbar avatar + workspace switcher.
"""

import frappe
from frappe import _


def get_context(context):
    # No edge caching — cockpit is per-user, live data
    context.no_cache = 1

    # Hide every piece of Frappe website chrome
    context.show_sidebar = False
    context.no_breadcrumbs = True
    context.no_header = True
    context.no_footer = True
    context.full_width = True
    context.parents = []
    context.title = "Repair Jobs · Baro Service"
    context.body_class = "baro-cockpit-page"

    # Authentication
    if frappe.session.user in ("Guest", None, ""):
        frappe.local.flags.redirect_location = "/login?redirect-to=/repair-jobs"
        raise frappe.Redirect

    # Permission gate — must have Repair Job read
    if not frappe.has_permission("Repair Job", "read"):
        frappe.throw(
            _("You do not have permission to access the Repair Jobs cockpit. "
              "Ask an admin to assign you a Baro role profile (e.g., Baro Estimate Manager)."),
            frappe.PermissionError,
        )

    # User context for the topbar
    user_doc = frappe.db.get_value(
        "User",
        frappe.session.user,
        ["full_name", "user_image", "username"],
        as_dict=True,
    ) or {}
    full_name = user_doc.get("full_name") or frappe.session.user
    context.user = frappe.session.user
    context.user_full_name = full_name
    context.user_initials = _initials(full_name)
    context.user_image = user_doc.get("user_image") or ""

    # Site context
    company = frappe.db.get_single_value("Global Defaults", "default_company") or "Baro Service LLC"
    context.company = company

    # Build a list of "Repair Job can-write" so the cockpit can disable inline-edit
    # for read-only users client-side too (defense in depth alongside set_field check)
    context.can_write_repair_job = 1 if frappe.has_permission("Repair Job", "write") else 0

    return context


def _initials(name: str) -> str:
    parts = (name or "").split()
    if not parts:
        return "U"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()
