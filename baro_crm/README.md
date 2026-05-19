# baro_crm

Custom Frappe app that adds the Baro Service operations cockpit to a self-hosted ERPNext site.

## What it provides

- **Repair Jobs cockpit** at `/repair-jobs` — chrome-free workspace with state-segmented (TX/FL/NY/NJ) list, inline-editable inspector, real-time workflow status changes, comments and field-change history.
- **`service_state` Custom Field** on the existing `Repair Job` DocType (Select: Texas, Florida, New York, New Jersey).
- **Whitelisted REST methods** under `baro_crm.api.repair_job.*` consumed by the cockpit.
- **Workspace shortcut** "Baro CRM" in the ERPNext sidebar.

This app **does not** define the `Repair Job` DocType itself — that lives in your existing ERPNext site already. This app only adds the cockpit UI + the new state field on top.

## Install (development)

From the Florida ERPNext server (Tailscale `100.127.172.110`):

```bash
cd ~/frappe_docker
# 1. Drop the app source into the bench's apps directory
docker compose -f pwd.yml cp /path/to/baro_crm backend:/home/frappe/frappe-bench/apps/
# 2. Install on the site
docker compose -f pwd.yml exec backend bench --site frontend install-app baro_crm
# 3. Run patches (backfill service_state from area)
docker compose -f pwd.yml exec backend bench --site frontend migrate
# 4. Clear cache
docker compose -f pwd.yml exec backend bench --site frontend clear-cache
```

After install, open `http://100.127.172.110:8080/repair-jobs` (must be logged in with Repair Job read permission).

See `DEPLOY.md` for full step-by-step deployment from your Windows workstation via Tailscale.

## Uninstall (safe rollback)

```bash
docker compose -f pwd.yml exec backend bench --site frontend uninstall-app baro_crm
```

Uninstall **does not** delete the `service_state` Custom Field by default (Frappe convention). To also remove the field manually:

```bash
docker compose -f pwd.yml exec backend bench --site frontend execute \
  "frappe.delete_doc('Custom Field', 'Repair Job-service_state')"
```

`Repair Job` data is untouched in all rollback scenarios.

## Files of interest

- `baro_crm/hooks.py` — app registration, fixtures, asset includes
- `baro_crm/api/repair_job.py` — REST endpoints consumed by the cockpit
- `baro_crm/www/repair-jobs.html` + `.py` — the cockpit page
- `baro_crm/public/css/cockpit.css` — scoped styles (`.baro-cockpit` namespace)
- `baro_crm/public/js/cockpit.js` — interactive logic
- `baro_crm/fixtures/custom_field.json` — auto-creates `service_state` on install
- `baro_crm/patches/v0_0_1/backfill_state.py` — populates `service_state` from `area` on existing rows
