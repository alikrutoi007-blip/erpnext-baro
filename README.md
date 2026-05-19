# Erpnext Baro

Local integration workspace for Baro Service ERPNext/CRM MVP.

## Purpose

This project connects the current Baro call workflow to ERPNext.

MVP path:

`Zadarma -> Make -> Google Sheets -> Python bot -> ERPNext API`

Current self-hosted ERPNext MVP site:

`http://100.127.172.110:8080`

Old Frappe Cloud trial site:

`https://baroservice.v.frappe.cloud`

## Security

- `.env` contains ERPNext API credentials and must never be committed or shared.
- API keys must not be stored in Obsidian, Google Sheets, screenshots, or source code.
- Use a dedicated ERPNext API user with minimal required permissions.

## Files

- `src/erpnext_client.py` - small ERPNext/Frappe REST API client.
- `scripts/check_connection.py` - verifies API credentials and basic access.
- `scripts/discover_site.py` - checks which standard DocTypes are available.
- `scripts/create_repair_job_doctype.py` - creates the central Baro `Repair Job` DocType.
- `scripts/create_role_profiles.py` - creates Baro role profiles for the MVP team structure.
- `scripts/create_repair_job_workflow.py` - creates workflow states, actions, and status transitions for `Repair Job`.
- `scripts/ingest_sheet_to_erpnext.py` - dry-run/execute bridge from `Zadarma real time calls` into ERPNext Customer/Contact/Address/Repair Job records.
- `scripts/setup_demo_environment.py` - creates/updates the leadership demo workspace, kanban, number cards, demo repair jobs, project, and tasks.
- `scripts/verify_demo_environment.py` - read-only check for the leadership demo workspace, demo records, ToDos, service items, employees, and invoice.
- `scripts/enhance_repair_job_experience.py` - improves the `Repair Job` form layout, required intake fields, quick buttons, role kanban boards, and role workspaces.
- `scripts/verify_repair_job_experience.py` - read-only check for the `Repair Job` UX enhancements.
- `scripts/verify_mvp_setup.py` - read-only check for the MVP DocType, role profiles, workflow states, and workflow.
- `config/repair_job_schema.json` - proposed Baro Repair Job schema.
- `docs/implementation_plan.md` - local implementation plan.
- `docs/field_mapping.md` - mapping from call bot/Sheets fields to ERPNext.
- `docs/sheets_to_erpnext_ingest.md` - commands and rules for the Sheets -> ERPNext ingest worker.
- `docs/demo_environment.md` - leadership demo walkthrough and commands for the ERPNext demo environment.
- `docs/setup_log_2026-04-19.md` - current setup log and safe resume commands.
- `docs/lead_group_automation.md` - automation plan for creating a client work group/task pack on each qualified new lead.

## First Commands

Store API token from ERPNext clipboard safely:

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
powershell -ExecutionPolicy Bypass -File .\scripts\set_api_token_from_clipboard.ps1
```

The script expects the ERPNext API dialog's `Copy token to clipboard` value and does not print secrets.

Check connection:

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
python .\scripts\check_connection.py
```

Discover basic DocTypes:

```powershell
python .\scripts\discover_site.py
```

Create or verify the Repair Job workflow:

```powershell
python .\scripts\create_repair_job_workflow.py
python .\scripts\create_repair_job_workflow.py --execute
```

Read-only MVP verification:

```powershell
python .\scripts\verify_mvp_setup.py
```

Dry-run one Google Sheet call into an ERPNext payload:

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
& "C:\Users\epmek\Documents\baro-call-sheet-bot\.venv\Scripts\python.exe" .\scripts\ingest_sheet_to_erpnext.py --limit 1 --max-rows 30
```

Dry-run a specific Sheet row:

```powershell
& "C:\Users\epmek\Documents\baro-call-sheet-bot\.venv\Scripts\python.exe" .\scripts\ingest_sheet_to_erpnext.py --row 3
```

Safest execute mode: import by exact Zadarma call ID, not by row number:

```powershell
& "C:\Users\epmek\Documents\baro-call-sheet-bot\.venv\Scripts\python.exe" .\scripts\ingest_sheet_to_erpnext.py --call-id "149337-..." --execute
```

Patch existing `Repair Job` schema after field changes:

```powershell
python .\scripts\patch_repair_job_schema.py
python .\scripts\patch_repair_job_schema.py --execute
```

Create/update the leadership demo environment:

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
python .\scripts\setup_demo_environment.py
python .\scripts\setup_demo_environment.py --execute
```

Improve the Repair Job form and role views:

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
python .\scripts\enhance_repair_job_experience.py
python .\scripts\enhance_repair_job_experience.py --execute
```

Verify the leadership demo environment before a meeting:

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
python .\scripts\verify_repair_job_experience.py
python .\scripts\verify_demo_environment.py
```

Run the full self-host MVP setup after the token is in `.env`:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_selfhost_mvp.ps1
```

Or copy the ERPNext token first and let the setup script store it:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_selfhost_mvp.ps1 -UseClipboardToken
```

Create MVP project/backlog tasks in ERPNext:

```powershell
python .\scripts\create_mvp_backlog_tasks.py --execute
```

## Current Strategy

Do not fork ERPNext core.

Start with ERPNext UI customization plus API bridge. Move stable customizations into a custom Frappe app later if needed.
