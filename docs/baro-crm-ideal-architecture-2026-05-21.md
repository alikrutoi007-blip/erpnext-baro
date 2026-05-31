# Baro CRM Ideal Architecture
Date: 2026-05-21
Status: Product architecture draft for Baro Service CRM/ERPNext.

## 1. Executive Decision

Baro CRM should not become a separate CRM that fights ERPNext. The best architecture is:

- ERPNext remains the source of truth for Customers, Contacts, Addresses, Employees, Items, Sales Invoices, Payment Entries, and accounting evidence.
- `Repair Job` remains the central Baro operational object.
- `baro_crm` custom Frappe app provides the beautiful day-to-day cockpit, Customer Chart, Work Group pages, saved views, dedup UX, and payroll score dashboards.
- Google Sheets remains temporary intake/audit until direct ingestion is stable.
- Teams remains communication, not source of truth. CRM can create/sync Teams groups later, but the CRM owns the official record.

The final system should feel like one operational command center, not ERPNext screens patched together.

## 2. Ideal CRM Shape

The CRM should have 8 main areas:

1. **Repair Jobs Cockpit** - daily dispatch, kanban/list, state/city filters, new lead intake, urgent follow-ups.
2. **Customer Chart** - one medical-chart-style history for every customer: calls, SMS, jobs, addresses, equipment, invoices, payments, warranty, notes.
3. **Work Groups** - internal team space per qualified job/client: dispatcher, estimate manager, production manager, technician, supply, accounting, regular client manager.
4. **Production Board** - technicians, parts, schedule, stuck jobs, warranty callbacks, field evidence/photos.
5. **Money Desk** - diagnostics paid, estimates approved, invoices sent, payments collected, overdue, refunds, warranty cost.
6. **Payroll & Scoreboard** - points 100-400, criteria completion, payout pool, employee share, locked accounting periods.
7. **Executive Insights** - revenue, lead sources, conversion, margin, technician performance, repeat customers, cities/states.
8. **Admin Rules** - workflow, score criteria, city routing, source mapping, role permissions, import logs, integration health.

## 3. End-to-End Business Flow

```text
Zadarma call
  -> Make.com / Google Sheet / transcript bot
  -> Lead Intake inside Repair Job
  -> dedup check against Customer + Contact + active Repair Jobs
  -> dispatcher qualifies lead
  -> diagnostic offer / prepayment
  -> Repair Job becomes qualified
  -> Client Work Group / Project created
  -> technician assigned
  -> diagnosis completed
  -> estimate sent / approved
  -> parts needed / ordered / received
  -> repair completed
  -> invoice sent
  -> payment collected
  -> warranty active
  -> closed / future repeat history remains on Customer Chart
```

## 4. Data Model

### Standard ERPNext Objects

- **Customer** - official customer/business identity.
- **Contact** - phone/email people linked to Customer.
- **Address** - validated service/billing addresses.
- **Employee** - staff member.
- **Item** - services, diagnostics, parts, repair labor.
- **Sales Invoice** - billing document.
- **Payment Entry** - actual collected money.
- **Project / Task / ToDo** - work group, handoffs, follow-ups.

### Baro Custom Objects / Extensions

- **Repair Job** - central operational card.
- **Customer Equipment** - later: machine inventory per customer/location.
- **Technician Visit** - later: field visit, arrival, photos, diagnosis, parts used.
- **Warranty Case** - later: callbacks and warranty cost tracking.
- **Compensation Period** - payroll period, revenue pool, locked/unlocked state.
- **Employee Scorecard** - employee points for period, criteria hits, payout share.
- **Score Criterion** - configurable rules that add/subtract points.
- **Score Event** - evidence that a criterion was met/missed.
- **Commission Allocation** - final payout calculation connected to collected revenue.

## 5. Repair Job Lifecycle

The cockpit should not show all 20 statuses equally. It should group them into business lanes:

- **Intake**: New, Need Follow-up.
- **Sales**: Diagnostics Offered, Waiting Prepayment, Diagnostics Paid.
- **Production**: Technician Assigned, On The Way, Diagnostics In Progress, Diagnosis Completed, Estimate Sent, Waiting Client Approval, Parts Needed, Parts Ordered, Repair Scheduled, Repair In Progress, Repair Completed.
- **Money & Care**: Invoice Sent, Paid, Warranty Active.
- **Out**: Closed, Lost, Spam, Unrelated.

Default view should show active jobs only. Spam/Unrelated/Lost/Closed should be searchable but not pollute the daily board.

## 6. Lead Intake and State/City Routing

States now:

- Texas
- Florida
- New York
- New Jersey

Each Repair Job should carry:

- `service_state`
- `city_area`
- `business_phone_did`
- `marketing_source`
- `assigned_dispatcher`
- `source_call_id` / `zadarma_call_id`
- `source_recording_url`
- `lead_quality`

Dispatcher workflow:

1. Incoming call appears as `New`.
2. CRM shows possible matches before creation/qualification.
3. Dispatcher picks existing customer or creates new.
4. Dispatcher assigns state/city.
5. If spam/unrelated, move to Out and hide from active board.
6. If qualified, proceed to diagnostic/prepayment.

## 7. Dedup Rules

Automatic linking is allowed only when confidence is high:

- explicit typeahead pick;
- exactly one normalized phone match;
- exactly one exact normalized business-name match.

Warnings only:

- similar names;
- multiple phone matches;
- same phone + equipment on active job within 90 days;
- same customer + same equipment on active job;
- same address + same business name.

No silent fuzzy merge. A dispatcher must choose when the system is unsure.

## 8. Customer Chart

The Customer Chart is the future "one page for everything". It should show:

- identity: business name, phones, emails, managers, source, tags;
- locations: addresses, city/state, access instructions;
- equipment: machine type, brand, model, serial, warranty notes;
- timeline: all calls, SMS, Repair Jobs, estimates, invoices, payments, warranties;
- open work: active Repair Jobs, tasks, follow-ups;
- money: collected revenue, outstanding balance, lifetime value;
- trust signals: repeat customer, complaint history, warranty risk, VIP status.

This is how the company stops losing history in Teams and Google Sheets.

## 9. Work Group Automation

A Client Work Group should be created when a lead becomes qualified. Recommended trigger:

- `Diagnostics Paid`, or
- `Technician Assigned` if diagnostic payment is skipped/handled differently.

Group members:

- dispatcher;
- estimate manager;
- production manager;
- technician;
- supply;
- accounting;
- regular client manager;
- ROP/manager when escalation is needed.

CRM actions:

- create Project/Work Group;
- create default ToDos;
- store group link on Repair Job;
- optionally create/sync Teams chat/channel later;
- every task remains in CRM even if people talk in Teams.

## 10. Accounting and Payroll Architecture

Important clarification: employees do not have fixed salary. They receive a percentage of company income depending on points from 100 to 400. Points increase when they meet assigned criteria.

### Recommended Accounting Source

Do not calculate payout from invoices sent. Use **collected money** from `Payment Entry`.

Better options:

1. **Collected Revenue Pool** - simplest: payout pool is a percent of paid revenue.
2. **Gross Profit Pool** - better: payout pool is a percent of revenue after parts, refunds, discounts, taxes, payment fees, and warranty cost.

Recommendation: start with Collected Revenue Pool for MVP, then move to Gross Profit Pool when cost tracking is clean.

### Payroll Formula

```text
Period Collected Revenue = sum(Payment Entries in locked period)
Company Payout Pool = Period Collected Revenue * payout_pool_percent
Employee Score = base points + earned points - penalties
Employee Score is capped between 100 and 400
Employee Share = employee_score / total_scores_of_eligible_employees
Employee Payout = Company Payout Pool * Employee Share
```

Example:

```text
Collected revenue: $180,000
Payout pool: 18% = $32,400
Total eligible points: 2,400
Dispatcher A: 320 points
Dispatcher A payout: 32,400 * 320 / 2,400 = $4,320
```

### Role-Specific Score Criteria

Dispatcher criteria:

- answered/processed qualified calls;
- complete phone/name/address/equipment;
- correct state/city/source;
- diagnostic/prepayment collected or properly followed up;
- duplicate prevented;
- follow-up completed before SLA.

Estimate Manager criteria:

- estimate sent within SLA;
- approval rate;
- gross margin protected;
- no forgotten follow-ups;
- clean explanation in Customer Chart.

Production Manager criteria:

- jobs scheduled quickly;
- technician utilization;
- stuck jobs resolved;
- parts blockers escalated;
- warranty callbacks reduced.

Technician criteria:

- on-time arrival;
- diagnosis quality;
- first-time fix;
- photos/evidence uploaded;
- parts accuracy;
- customer rating;
- low warranty callback rate.

Supply criteria:

- correct parts identified;
- order placed fast;
- cost controlled;
- ETA communicated.

Accounting criteria:

- invoice sent same day;
- payment reconciled;
- overdue followed up;
- refund/void handled cleanly.

Regular Client Manager criteria:

- repeat customers followed up;
- VIP/warranty reminders handled;
- inactive valuable customers reactivated;
- relationship notes kept clean.

### Payroll Controls

- Accounting creates a Compensation Period.
- System pulls collected revenue.
- Managers review score events.
- Period is locked.
- Payouts are exported or posted as commission/additional salary entries.
- Any manual adjustment requires reason + manager approval.

This keeps the system fair and auditable.

## 11. Existing Customer Migration

For 5-6k existing customers:

1. Backup ERPNext first.
2. Export and normalize source data.
3. Dry-run import.
4. Import Customers first.
5. Import Contacts and phone numbers.
6. Import Addresses.
7. Add legacy fields:
   - `legacy_customer_id`
   - `normalized_phone`
   - `source_system`
   - `import_batch_id`
   - `duplicate_warning`
   - `service_state`
   - `city_area`
8. Do not fuzzy merge automatically.
9. Produce duplicate review queue.
10. Import historical jobs/invoices later only if useful.

## 12. Ideal Screens

### Main CRM Home

- Today revenue collected.
- New qualified leads by state.
- Active jobs by lane.
- Stuck jobs.
- Unassigned jobs.
- Payroll pool preview.
- Integration health.

### Repair Jobs Cockpit

- List + Kanban.
- State tabs and city chips.
- Right inspector.
- Create Repair Job drawer.
- Dedup warnings.
- Quick actions.

### Customer Chart

- Identity header.
- Timeline.
- Active jobs.
- Equipment.
- Invoices/payments.
- Warranty.
- SMS/call history.

### Payroll Scoreboard

- Period selector.
- Collected revenue.
- Payout pool.
- Employee point ranking.
- Criteria checklist.
- Manager review.
- Lock/export.

### Manager Executive Page

- Revenue and gross profit.
- Conversion by source.
- Jobs by state/city.
- Technician performance.
- Warranty cost.
- Repeat customers.
- Lost/spam/unrelated trends.

## 13. Security and Permissions

- Dedicated integration user, not owner account.
- Role-based access to customer PII, transcripts, revenue, payroll.
- Payroll pages visible only to owner/accounting/ROP.
- Technicians see only assigned jobs and required customer/location info.
- Audit every workflow transition and payroll adjustment.
- Backups before import and before production launch.

## 14. Implementation Phases

### Phase 1 - Operational Cockpit

- Finish Create Repair Job drawer.
- Workspace/sidebar shortcut.
- Views and state/city filters.
- Basic dedup warnings.

### Phase 2 - Customer Foundation

- Import 5-6k customers.
- Normalize phones.
- Build Customer Chart.
- Full dedup/attach-to-existing.

### Phase 3 - Work Groups

- Auto-create Project/Work Group.
- ToDo templates.
- Teams link/sync.

### Phase 4 - Money Desk

- Invoices/payments visibility.
- Diagnostics/prepayment controls.
- Overdue follow-up.

### Phase 5 - Payroll Scoreboard

- Score criteria.
- Score events.
- Compensation periods.
- Payout formulas.
- Lock/export process.

### Phase 6 - Executive System

- Insights dashboard.
- Margin/profit model.
- Forecasting.
- Quality score by state/city/team.

## 15. Open Decisions

- Is payout pool based on collected revenue or gross profit?
- Is payout pool company-wide or role-specific pools?
- What is the payout period: weekly, biweekly, or monthly?
- Who can approve score adjustments?
- Which criteria add points automatically, and which require manager approval?
- Should Teams group creation be automatic or manager-confirmed?

## 16. Recommended Next Step

Use this architecture as the north-star while implementing the roadmap. The HTML prototype in `crm-prototype/ideal-crm-architecture.html` should guide product/UI decisions, but production should live inside the `baro_crm` Frappe app.
