# New Lead Client Group Automation

## Goal

When a new qualified lead enters ERPNext, the bot should create a clean internal work pack for that client so the team does not lose ownership, follow-up, or context.

## MVP Decision

Use ERPNext `Project`, `Task`, `ToDo`, and `Repair Job` links instead of building a custom chat system first.

This gives Baro Service a professional structure immediately:

- one `Repair Job` remains the operational source of truth;
- one linked `Project` becomes the client work group/task pack;
- each responsible person receives a `ToDo` or task assignment;
- every call, transcript, comment, estimate, invoice, and follow-up stays searchable.

## Trigger

Create the client work group only when the incoming row/call becomes a real lead or repair request.

Do not create a group for:

- `Spam`
- `Unrelated`
- obvious wrong number
- very short calls with no service intent

## Naming

Preferred:

`{Business Name} - {Area} - {Repair Job ID}`

Fallback if business name is unknown:

`{Caller Phone} - {Area} - {Repair Job ID}`

Examples:

- `Tradewinds Resort - FL-Tampa Bay - RJ-2026-00012`
- `7324849733 - NY - RJ-2026-00013`

## Members To Add

MVP default members:

- Dispatcher / ID
- Estimate Manager
- Production Manager
- Regular Client Manager
- ROP

Conditional members:

- Technician, after technician is assigned
- Mentor, if technician needs supervision
- Supply, when `parts_needed` is checked or `parts_status` is not `Not Needed`
- Accounting, when status reaches `Invoice Sent`, `Paid`, or payment follow-up is needed

## Default Tasks

Create these tasks or ToDos when a lead is qualified:

- Review transcript and call quality.
- Confirm business name, contact, phone, email, address, and area.
- Confirm equipment type, symptom, urgency, and requested service.
- Offer or confirm diagnostics/prepayment.
- Assign owner for follow-up.
- Assign production manager after diagnostics are sold.
- Assign technician after payment/approval.
- Send estimate after diagnosis.
- Follow up if estimate is not approved.
- Create invoice/payment follow-up after repair.
- Create warranty follow-up when repair is completed.

## Repair Job Fields

`Repair Job` stores the automation result:

- `client_group_name`
- `client_group_project`
- `client_group_created_at`
- `client_group_members`

These fields make the automation idempotent: if `client_group_project` already exists, the bot must update the existing work pack instead of creating a duplicate.

## Idempotency Rule

Before creating a client group:

1. Check whether the `Repair Job` already has `client_group_project`.
2. Search for an existing `Project` by the expected group name.
3. If found, link it back to `Repair Job`.
4. If not found, create a new `Project` and default tasks.

## Later Phase

After MVP validation, this can become a custom Frappe app hook:

- on `Repair Job` create: create client work pack;
- on status change: add/remove conditional tasks;
- on technician assignment: add technician task;
- on parts needed: add Supply task;
- on invoice sent: add Accounting task;
- on warranty start: schedule warranty follow-up.
