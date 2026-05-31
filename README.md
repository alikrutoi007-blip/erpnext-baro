# ERPNext Baro CRM

Custom ERPNext/Frappe CRM workspace for Baro Service operations: repair-job intake, dispatching, customer deduplication, customer migration, and service workflow automation.

Private credentials, customer migration outputs, logs, and live environment details are intentionally excluded from this repository.

## What This Project Does

Baro Service needed one operational command center for restaurant equipment repair calls, dispatching, follow-ups, customer records, and service workflow. This project extends ERPNext with a custom `baro_crm` app and supporting scripts instead of forking ERPNext core.

Core flow:

```text
Zadarma / call sheet data
  -> Google Sheets / Python automation
  -> ERPNext Customer / Contact / Address / Repair Job
  -> custom dispatcher cockpit
  -> workflow, follow-up, estimates, invoicing, and customer history
```

## Highlights

- **Repair Jobs cockpit**: custom list/kanban workspace for dispatchers with status lanes, state/city filters, named views, calendar/date filters, sorting, and compact repair-job cards.
- **Create Repair Job drawer**: fast intake UI with customer typeahead, phone normalization, duplicate warnings, active-job warnings, cautious address handling, and role-aware write controls.
- **Workflow automation**: ERPNext `Repair Job` states, workflow transitions, role profiles, dispatcher/reader permissions, and server-side status APIs.
- **Customer migration tooling**: CSV/template pipeline for deduplicating legacy customer records, normalized phone matching, legacy IDs, import batches, dry-run/execute modes, rollback support, and smoke tests.
- **Call-sheet ingestion**: Python bridge for transforming Zadarma/Google Sheets call records into ERPNext-ready Customers, Contacts, Addresses, and Repair Jobs.
- **Architecture docs and prototype**: CRM roadmap, ideal architecture notes, and HTML prototype artifacts for stakeholder review.
- **Deployment support**: install scripts for a self-hosted ERPNext/Frappe Docker setup, asset materialization, fixture sync, and post-deploy verification scripts.

## Tech Stack

- ERPNext / Frappe
- Python
- JavaScript
- HTML/CSS
- MariaDB
- Docker-based ERPNext deployment
- Google Sheets / Zadarma data workflow
- Git-based deployment workflow

## Repository Map

```text
baro_crm/                 Custom Frappe app: APIs, fixtures, public JS/CSS, install script
scripts/                  Setup, migration, verification, and smoke-test scripts
src/                      ERPNext/Frappe REST client helpers
docs/                     Architecture, roadmap, specs, and implementation notes
config/                   Repair Job schema/configuration artifacts
crm-prototype/            Static CRM prototype and architecture UI artifacts
tests/                    Unit tests for migration and API helper behavior
```

## Key Features

### Dispatcher Cockpit

The cockpit gives dispatchers a focused alternative to raw ERPNext forms. It supports kanban/list modes, workflow-aware status changes, role-based controls, view filters, date ranges, city filters, active/archive views, and high-speed repair-job creation.

### Customer Deduplication

The backend normalizes phone numbers, checks Customer and Contact links, detects possible duplicate customers, and warns about active Repair Jobs before creating a new job. It avoids auto-linking ambiguous matches so dispatchers stay in control.

### Customer Migration

The migration pipeline prepares legacy customer spreadsheets for ERPNext import with normalized phones, legacy customer IDs, source-system tracking, import batches, duplicate-warning flags, dry-run reports, execute mode, and rollback by batch.

### ERPNext-First Architecture

ERPNext remains the source of truth for Customers, Contacts, Addresses, Repair Jobs, Sales Invoices, Payment Entries, Employees, Items, and accounting evidence. The custom app adds a faster operational layer without replacing ERPNext core.

## Security

- `.env` and local credentials are ignored and must never be committed.
- Customer migration outputs are ignored because they may contain names, phones, and addresses.
- Logs are ignored by default.
- This public repo is intended to show implementation structure and engineering approach, not expose production data.

## Local Development Notes

This repo assumes an existing ERPNext/Frappe environment and a configured site. Typical local checks include:

```powershell
python .\scripts\check_connection.py
python .\scripts\verify_mvp_setup.py
python .\scripts\verify_customer_migration.py
```

Deployment to the internal ERPNext host is handled separately through the project install script and environment-specific credentials.

## Status

Shipped modules include the repair-job cockpit, create-repair-job drawer, workspace/role integration, named views/calendar filters, and the customer migration implementation. Future roadmap items include customer-site modeling, full customer chart history, deeper RingCentral/email integration, and Teams work-group automation.
