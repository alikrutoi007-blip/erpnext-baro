# Field Mapping

## Current Source

Google Sheet: `Zadarma real time calls`

## Target

ERPNext custom DocType: `Repair Job`

## Mapping

| Source Field | ERPNext Target | Notes |
| --- | --- | --- |
| Date | `call_datetime` | Parse from Zadarma recording URL when possible. |
| Status | workflow/status | Use Baro status normalization. |
| Area | `area` | From DID attribution. |
| Marketing channel | `marketing_source` | From sheet source column when present, otherwise from DID attribution. |
| Client information | `client_information_from_call` | AI extracted, not authoritative. `Person--Business` becomes Contact + business Customer. |
| Service summary | `service_summary` | AI extracted. |
| Phone number of client | `caller_phone` and Contact phone | Normalize later. |
| Quality of call | `call_quality` | AI score/reason. |
| Comment | `internal_comment` | Operational note. |
| Address | Address + `service_address` | Create Address only when confident. |
| Email | Contact email | Create/update only when heard. |
| Purpose of call | `purpose_of_call` | AI extracted. |
| Transcript | `call_transcript` | Store once, avoid re-transcription. |
| Recording URL | `zadarma_recording_url` | Primary idempotency key. |
| Duration | `call_duration_seconds` | From Make/Zadarma. |
| Qualified lead flag | `client_group_project` / Project | Create only for real leads, not spam/unrelated calls. |

## Idempotency

Before creating a Repair Job, search by:

1. `zadarma_recording_url`
2. `zadarma_call_id`
3. caller phone + DID + call datetime + duration

## MVP Ingest Script

Current script:

`scripts/ingest_sheet_to_erpnext.py`

Current behavior:

- Defaults to dry-run.
- Reads only `Zadarma real time calls`.
- Creates/updates `Repair Job` by `zadarma_recording_url` or `zadarma_call_id`.
- Creates Customer/Contact/Address payloads before Repair Job.
- Writes audit records to `logs/ingest.jsonl`.
- Infers missing `marketing_source` from the DID attribution map in the existing call bot.

See `docs/sheets_to_erpnext_ingest.md` for commands.

## New Lead Group

When a row/call becomes a real lead, the bot should create or update a linked Project/task pack:

- Project name: business name + area + Repair Job ID, or phone + area + Repair Job ID.
- Link the Project back to `Repair Job.client_group_project`.
- Create default ToDos for dispatcher, estimate manager, production manager, regular client manager, and ROP.
- Add technician, supply, and accounting tasks later when their workflow stage starts.
