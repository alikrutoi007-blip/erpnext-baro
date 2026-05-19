# API Connection Status

Date: 2026-04-19

## Result

ERPNext API connection worked earlier, but later calls on 2026-04-19 started returning `504 Gateway Timeout`.

Site:

`https://baroservice.v.frappe.cloud`

Authenticated user:

`alikrutoi007@gmail.com`

Visible company:

`Baro Service`

## Discovery Result

Standard DocTypes are visible through API:

- Customer
- Contact
- Address
- Lead
- Issue
- Maintenance Visit
- Call Log
- Employee
- Timesheet
- Item
- Sales Invoice
- Payment Entry
- Workflow
- Role Profile
- DocType

## Important Fix

The correct domain is:

`baroservice.v.frappe.cloud`

Incorrect domains tested:

- `baroservice.frappe.cloud` -> Frappe Cloud `site_not_found`
- `baroservice.vfrappe.cloud` -> DNS does not exist

## Next Step

Wait for Frappe Cloud/site runtime to recover, then run:

```powershell
python .\scripts\check_connection.py
python .\scripts\verify_mvp_setup.py
python .\scripts\create_repair_job_workflow.py --execute
python .\scripts\verify_mvp_setup.py
```

After `Repair Job` exists, connect the current Google Sheets call bot to ERPNext API.

## Security

API credentials are stored only in local `.env`, not in Obsidian.
