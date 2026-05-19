# Repair Operations Command Center Prototype

Date: 2026-05-19

File:
- `crm-prototype/repair-job-workspace.html`

Purpose:
- This is a production-style visual prototype for Baro Service repair operations.
- It is not a temporary ERPNext MVP screen.
- It defines the desired UI/UX direction for a future custom ERPNext page or external frontend connected to ERPNext API.

Core UX Decisions:
- The main screen is a Kanban command center for repair jobs.
- The workflow is separated by state, city, role, and status.
- The right-side panel acts as the operational customer/repair chart.
- The design prioritizes dispatch speed, production clarity, and manager visibility.

Supported Regions:
- Florida: Tampa, Orlando, Sarasota, Miami, St. Petersburg
- New York: New York City, Brooklyn, Queens
- New Jersey: Jersey City, Newark, New Brunswick
- Texas: Houston, Dallas, Austin

Primary Workflow Columns:
- New
- Need Follow-up
- Waiting Prepayment
- Ready to Dispatch
- Technician Assigned
- In Diagnostics
- Estimate / Approval
- Parts Needed
- Repair In Progress
- Repair Completed
- Paid / Warranty
- Lost / Out

Role Views:
- All Ops
- Dispatch
- Production
- Money

Right Panel Sections:
- Overview
- Call
- Money
- Team
- Timeline

Important Interactions:
- Drag-and-drop cards between Kanban columns.
- Region and city filtering.
- Urgent-only and unassigned-only filters.
- Right-panel status selector.
- Next-action advance button.
- Search by customer, phone, address, equipment, source, and repair job ID.

Future Implementation Options:
- Short term: use this file as the visual specification for stakeholders.
- ERPNext-native: recreate key views with ERPNext Kanban, Workspace, List View, and Client Scripts.
- Production-grade UI: build a custom Frappe Page or separate frontend connected to ERPNext REST API.

Production Notes:
- Real production integration should not change status directly if ERPNext Workflow is enforced.
- Drag-and-drop should call a safe workflow action endpoint, not just update the `status` field.
- Cards should be loaded from `Repair Job` records.
- The right panel should read Customer, Contact, Address, Repair Job, Sales Invoice, Payment Entry, Task, ToDo, and call transcript data.
- The frontend must respect role permissions for dispatcher, production manager, estimate manager, technician, and ROP.
