app_name = "baro_crm"
app_title = "Baro CRM"
app_publisher = "Baro Service"
app_description = "Baro Service operations CRM — Repair Job cockpit and executive insights"
app_email = "baroservicellc@gmail.com"
app_license = "MIT"
app_version = "0.0.1"

# -----------------------------------------------------------------------------
# Website routing — exposes /repair-jobs as a chrome-free workspace page
# -----------------------------------------------------------------------------
website_route_rules = [
    {"from_route": "/repair-jobs", "to_route": "repair-jobs"},
]

# Pages we do NOT want indexed
website_route_rules += [
    {"from_route": "/repair-jobs/<path:rest>", "to_route": "repair-jobs"},
]

# -----------------------------------------------------------------------------
# Fixtures — ship the service_state Custom Field with the app
# -----------------------------------------------------------------------------
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
        "dt": "Role",
        "filters": [["name", "in", ["Baro Dispatcher", "Baro Reader"]]],
    },
]

# -----------------------------------------------------------------------------
# Role-based default landing page
# Users with the Baro Dispatcher role land on /repair-jobs after login instead
# of /app. Add more roles here as needed — Frappe picks the first match from
# the user's enabled roles.
# -----------------------------------------------------------------------------
role_home_page = {
    "Baro Dispatcher": "/repair-jobs",
}

# -----------------------------------------------------------------------------
# Install / migrate hooks
# Ensures the Baro Dispatcher role + Custom DocPerm rows exist after every
# bench migrate so dispatchers always have the minimum perms needed to drive
# /repair-jobs end-to-end. Idempotent — safe to run on every migrate.
# -----------------------------------------------------------------------------
after_install = "baro_crm.install.after_install"
after_migrate = "baro_crm.install.after_migrate"

# -----------------------------------------------------------------------------
# Permissions / boot — no extra global hooks for MVP
# -----------------------------------------------------------------------------

# Optional: listen to Repair Job updates and broadcast cockpit-specific events.
# Frappe already broadcasts 'doc_update' on every save — we'll consume that in JS.

# doc_events = {
#     "Repair Job": {
#         "after_insert": "baro_crm.api.repair_job.on_repair_job_created",
#         "on_update": "baro_crm.api.repair_job.on_repair_job_updated",
#     }
# }
