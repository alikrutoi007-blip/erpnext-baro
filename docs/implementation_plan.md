# ERPNext Baro Implementation Plan

## Decision

Use ERPNext standard DocTypes plus a custom central `Repair Job` DocType.

Do not fork ERPNext core.

## MVP Build Order

1. Verify ERPNext API credentials against the self-hosted site.
2. Confirm standard DocTypes are visible through API.
3. Create or manually configure `Repair Job` in ERPNext.
4. Add fields from `config/repair_job_schema.json`. Included in `Repair Job` creation payload.
5. Create workflow statuses.
6. Connect the existing Google Sheets call bot to ERPNext API.
7. Push one test call as a dry-run.
8. Push one real test call to ERPNext.
9. Create a client work group/task pack automatically for every qualified new lead.
10. Validate with dispatcher/manager workflow.

## What User Does

- Keep ERPNext test site active.
- Confirm API user has enough permissions.
- Approve final `Repair Job` fields.
- Create missing role profiles/users if needed.
- Review test records inside ERPNext.

## What Codex Can Do

- Build API client.
- Build dry-run import tools.
- Build Google Sheets -> ERPNext bridge.
- Create schema docs and migration scripts.
- Generate API payloads for Repair Job.
- Add automation for new lead client work groups using Project, Task, and ToDo.
- Test connection and discover permissions.
- Later scaffold custom Frappe app if needed.

## Safety

- `.env` is ignored.
- Default mode is dry-run.
- No production write should run until dry-run output is reviewed.
- Workflow setup is idempotent and can be safely resumed.
- New lead group creation must be idempotent: never create duplicate Projects/Tasks for the same Repair Job.
