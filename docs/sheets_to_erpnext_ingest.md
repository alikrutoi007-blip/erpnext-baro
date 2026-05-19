# Sheets to ERPNext Ingest

## Purpose

This script is the first MVP bridge from the live Zadarma Google Sheet into ERPNext.

Pipeline:

`Zadarma -> Make.com -> Google Sheets -> call bot transcript/summary -> ERPNext API`

Source sheet:

`Zadarma real time calls`

Target records:

- `Customer`
- `Contact`
- `Address` when an address is present
- `Repair Job`

## Safety Mode

Default mode is dry-run.

Dry-run reads Google Sheets and ERPNext, builds the payload, writes an audit line to `logs/ingest.jsonl`, but does not create or update ERPNext records.

Execute mode requires `--execute`.

Do not use `--execute` until:

- ERPNext backup was taken.
- Dedicated integration user exists.
- One known row was checked in dry-run.
- The output payload looks correct.

## Run Commands

Run from PowerShell:

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
& "C:\Users\epmek\Documents\baro-call-sheet-bot\.venv\Scripts\python.exe" .\scripts\ingest_sheet_to_erpnext.py --limit 1 --max-rows 30
```

Run one exact Google Sheet row:

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
& "C:\Users\epmek\Documents\baro-call-sheet-bot\.venv\Scripts\python.exe" .\scripts\ingest_sheet_to_erpnext.py --row 3
```

Do not execute a live row number by itself. New Make/Zadarma rows can arrive at the top and move row numbers while you are testing.

Execute a checked row only with an expected call ID:

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
& "C:\Users\epmek\Documents\baro-call-sheet-bot\.venv\Scripts\python.exe" .\scripts\ingest_sheet_to_erpnext.py --row 3 --expect-call-id "149337-..." --execute
```

Better: execute by exact Zadarma call ID so row movement does not matter:

```powershell
cd "C:\Users\epmek\Documents\Erpnext Baro"
& "C:\Users\epmek\Documents\baro-call-sheet-bot\.venv\Scripts\python.exe" .\scripts\ingest_sheet_to_erpnext.py --call-id "149337-..." --execute
```

## Current Mapping Behavior

- Customer is created from business name when the AI field looks like `Person--Business`.
- Contact is created from the person name.
- Phone numbers are normalized to `+1...` for US numbers.
- The script detects which phone number is a Baro DID by checking the existing DID attribution map.
- The DID becomes `business_phone_did`; the other number becomes `caller_phone`.
- `area` is taken from the sheet if present.
- `marketing_source` is taken from the sheet if present.
- If `source` is missing, `area` and `marketing_source` are inferred from the destination DID using the existing call bot attribution map.
- `zadarma_recording_url` is the primary idempotency key.
- `zadarma_call_id` is parsed from the recording URL and used as the safe exact selector for execute.
- `zadarma_recording_url` is stored as `Small Text` because Zadarma URLs are longer than ERPNext's 140-character `Data` limit.
- `zadarma_call_id` remains `Data` + unique and is the strongest dedupe key.
- Spam, unrelated calls, wrong numbers, and business listing calls are not treated as qualified leads.

## Current Dry-Run Example

For a call with:

- Client information: `Barbara--Courtyard by Marriott`
- DID: `+13479194188`
- Area: `USA, New York + SMS`

The script now prepares:

- Customer: `Courtyard by Marriott`
- Contact: `Barbara`
- Area: `USA, New York + SMS`
- Marketing source: `BaroSite NY`
- Repair Job status: `New`

For a row where the sheet has both:

- Client phone: `+12123805011`
- Baro DID: `+13479194188`

The script checks the DID map and stores:

- `caller_phone`: `+12123805011`
- `business_phone_did`: `+13479194188`
- `marketing_source`: `BaroSite NY`

## Next Implementation Step

After one safe execute test, add write-back columns to the Sheet:

- `ERPNext Repair Job`
- `ERPNext ingest status`
- `ERPNext ingest error`
- `ERPNext synced at`

This keeps Google Sheets as a temporary queue/audit layer until ERPNext becomes the source of truth.

## First Successful Execute

First real Repair Job created:

- `RJ-2026-00001`
- Customer: `Marriott Residence Inn`
- Contact: `Mike-Marriott Residence Inn`
- Address: `Marriott Residence Inn-Billing`
- Call ID: `149337-1779113543.14005629-12123805011-2026-05-18-101223`

Verification:

- Re-running dry-run for the same call ID returns `action: update`, not `create`.
