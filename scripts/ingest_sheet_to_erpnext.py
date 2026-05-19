from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS_ROOT = ROOT.parent
DEFAULT_CALL_BOT_ROOT = DOCUMENTS_ROOT / "baro-call-sheet-bot"
sys.path.insert(0, str(ROOT / "src"))

from erpnext_client import ERPNextClient, ERPNextConfig


def bypass_system_proxies() -> None:
    # Local Codex/Windows sessions can set dummy proxy values like 127.0.0.1:9.
    # Both Google OAuth and ERPNext/Tailscale calls must use direct networking.
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        os.environ.pop(key, None)
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"


def load_env_file(path: Path, *, override: bool = False) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if override or key not in os.environ:
            os.environ[key] = value


def load_call_bot_module(call_bot_root: Path) -> Any:
    src = call_bot_root / "src"
    if not src.exists():
        raise RuntimeError(f"Call bot src folder was not found: {src}")
    sys.path.insert(0, str(src))
    load_env_file(call_bot_root / ".env", override=False)
    import call_sheet_bot  # type: ignore

    return call_sheet_bot


@dataclass(frozen=True)
class SheetColumns:
    date: int | None
    status: int | None
    area: int | None
    source: int | None
    client: int | None
    service: int | None
    destination: int | None
    quality: int | None
    comment: int | None
    caller: int | None
    address: int | None
    email: int | None
    purpose: int | None
    transcript: int | None
    link: int
    duration: int | None


@dataclass(frozen=True)
class SheetCallRow:
    row_number: int
    date: str
    status: str
    area: str
    source: str
    client_information: str
    service_summary: str
    destination_number: str
    call_quality: str
    comment: str
    caller_phone: str
    address: str
    email: str
    purpose: str
    transcript: str
    recording_url: str
    duration_seconds: int | None
    call_datetime: str
    zadarma_call_id: str


def cell_text(call_sheet_bot: Any, rows: list[list[dict[str, str]]], row_index: int, col: int | None) -> str:
    if col is None:
        return ""
    return call_sheet_bot.row_cell(rows, row_index, col).get("text", "").strip()


def cell_url_or_text(call_sheet_bot: Any, rows: list[list[dict[str, str]]], row_index: int, col: int | None) -> str:
    if col is None:
        return ""
    cell = call_sheet_bot.row_cell(rows, row_index, col)
    return (cell.get("url") or cell.get("text") or "").strip()


def detect_columns(call_sheet_bot: Any, headers: list[str], rows: list[list[dict[str, str]]]) -> SheetColumns:
    optional = call_sheet_bot.find_header_index_optional
    return SheetColumns(
        date=call_sheet_bot.detect_date_index(headers, os.getenv("DATE_HEADER", "date")),
        status=optional(headers, os.getenv("STATUS_HEADER", "Status"), ["status"]),
        area=optional(headers, os.getenv("AREA_HEADER", "Area"), ["area", "location", "city"]),
        source=optional(headers, os.getenv("MARKETING_CHANNEL_HEADER", "source"), ["source", "marketing channel", "channel"]),
        client=optional(headers, os.getenv("CLIENT_INFORMATION_HEADER", "Client information"), ["client information", "client info", "customer information"]),
        service=optional(headers, os.getenv("SERVICE_HEADER", "service"), ["service", "service type", "вид услуги", "что делаем"]),
        destination=optional(headers, os.getenv("DESTINATION_NUMBER_HEADER", "Phone number"), ["phone number", "destination", "destination number", "business phone"]),
        quality=optional(headers, os.getenv("QUALITY_HEADER", "Quality of call"), ["quality of call", "call quality"]),
        comment=optional(headers, os.getenv("COMMENT_HEADER", "Comment"), ["comment"]),
        caller=optional(headers, os.getenv("CALLER_PHONE_HEADER", "caller number"), ["caller number id", "caller number", "client phone", "номер телефона"]),
        address=optional(headers, os.getenv("ADDRESS_HEADER", "address"), ["address", "адрес"]),
        email=optional(headers, os.getenv("EMAIL_HEADER", "email"), ["email", "e-mail"]),
        purpose=optional(headers, os.getenv("PURPOSE_HEADER", "Purpose of call"), ["purpose", "purpose of call"]),
        transcript=optional(headers, os.getenv("TRANSCRIPT_HEADER", "Transcript"), ["transcript", "transcription"]),
        link=call_sheet_bot.detect_call_link_index(headers, rows, os.getenv("CALL_LINK_HEADER", "call link")),
        duration=optional(headers, os.getenv("ZADARMA_CALL_TIME_HEADER", "duration"), ["duration", "duration of a call", "call time"]),
    )


def parse_int(value: str) -> int | None:
    if not value:
        return None
    match = re.search(r"\d+", value)
    return int(match.group(0)) if match else None


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D+", "", value or "")
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    if digits:
        return "+" + digits
    return ""


def attribution_for_phone(call_sheet_bot: Any, value: str) -> Any | None:
    if not value:
        return None
    return call_sheet_bot.attribution_for_destination_number(value)


def zadarma_call_id_from_url(url: str) -> str:
    filename = Path(urlparse(url).path).name
    return filename.removesuffix(".mp3")


def status_to_repair_status(status: str, service_summary: str) -> str:
    normalized = " ".join(f"{status} {service_summary}".lower().split())
    if "spam" in normalized:
        return "Spam"
    if "unrelated" in normalized or "not related" in normalized or "wrong number" in normalized:
        return "Unrelated"
    if "warranty" in normalized:
        return "Warranty Active"
    if "payment" in normalized or "invoice" in normalized:
        return "Invoice Sent"
    if "parts" in normalized:
        return "Parts Needed"
    if "estimate" in normalized or "quote" in normalized:
        return "Estimate Sent"
    if "repair" in normalized:
        return "Repair In Progress"
    if "diagn" in normalized:
        return "New"
    return "Need Follow-up"


def is_qualified_lead(row: SheetCallRow) -> bool:
    combined = " ".join(
        [
            row.status,
            row.service_summary,
            row.purpose,
            row.comment,
        ]
    ).lower()
    blocked = ("spam", "unrelated", "not related", "wrong number", "business listing")
    if any(token in combined for token in blocked):
        return False
    return bool(row.recording_url and (row.purpose or row.service_summary or row.transcript))


def parse_client_identity(client_information: str, phone: str, row_number: int) -> tuple[str, str, str]:
    """Return customer name, customer type, and contact/person name from AI text."""
    raw = re.sub(r"\s+-\s+-\s+", "--", (client_information or "").strip())
    raw = re.sub(r"\s*--+\s*", "--", raw)
    if "--" in raw:
        parts = [part.strip(" -") for part in raw.split("--") if part.strip(" -")]
    else:
        parts = [part.strip(" -") for part in re.split(r"\s+-+\s+", raw) if part.strip(" -")]

    if len(parts) >= 2:
        contact_name = parts[0]
        customer_name = parts[-1]
        return customer_name, "Company", contact_name
    if len(parts) == 1:
        return parts[0], "Individual", parts[0]
    if phone:
        unknown = f"Unknown Caller {phone}"
        return unknown, "Individual", unknown
    unknown = f"Unknown Caller Row {row_number}"
    return unknown, "Individual", unknown


def parse_client_name(client_information: str, phone: str, row_number: int) -> tuple[str, str]:
    customer_name, customer_type, _contact_name = parse_client_identity(client_information, phone, row_number)
    return customer_name, customer_type


def make_sheet_row(
    call_sheet_bot: Any,
    rows: list[list[dict[str, str]]],
    row_index: int,
    columns: SheetColumns,
) -> SheetCallRow:
    recording_url = cell_url_or_text(call_sheet_bot, rows, row_index, columns.link)
    call_dt = call_sheet_bot.parse_zadarma_datetime_from_url(recording_url)
    first_phone = normalize_phone(cell_text(call_sheet_bot, rows, row_index, columns.destination))
    second_phone = normalize_phone(cell_text(call_sheet_bot, rows, row_index, columns.caller))
    first_attribution = attribution_for_phone(call_sheet_bot, first_phone)
    second_attribution = attribution_for_phone(call_sheet_bot, second_phone)

    if first_attribution and not second_attribution:
        business_did = first_phone
        caller_phone = second_phone
    elif second_attribution and not first_attribution:
        business_did = second_phone
        caller_phone = first_phone
    else:
        caller_phone = first_phone or second_phone
        business_did = second_phone if second_phone and second_phone != caller_phone else ""

    business_attribution = attribution_for_phone(call_sheet_bot, business_did)
    area = cell_text(call_sheet_bot, rows, row_index, columns.area)
    source = cell_text(call_sheet_bot, rows, row_index, columns.source)
    if business_attribution is not None:
        area = area or business_attribution.area
        source = source or business_attribution.source

    return SheetCallRow(
        row_number=row_index + 1,
        date=cell_text(call_sheet_bot, rows, row_index, columns.date),
        status=cell_text(call_sheet_bot, rows, row_index, columns.status),
        area=area,
        source=source,
        client_information=cell_text(call_sheet_bot, rows, row_index, columns.client),
        service_summary=cell_text(call_sheet_bot, rows, row_index, columns.service),
        destination_number=business_did,
        call_quality=cell_text(call_sheet_bot, rows, row_index, columns.quality),
        comment=cell_text(call_sheet_bot, rows, row_index, columns.comment),
        caller_phone=caller_phone,
        address=cell_text(call_sheet_bot, rows, row_index, columns.address),
        email=cell_text(call_sheet_bot, rows, row_index, columns.email),
        purpose=cell_text(call_sheet_bot, rows, row_index, columns.purpose),
        transcript=cell_text(call_sheet_bot, rows, row_index, columns.transcript),
        recording_url=recording_url,
        duration_seconds=parse_int(cell_text(call_sheet_bot, rows, row_index, columns.duration)),
        call_datetime=call_dt.strftime("%Y-%m-%d %H:%M:%S") if call_dt else "",
        zadarma_call_id=zadarma_call_id_from_url(recording_url),
    )


def clean_doc(doc: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in doc.items() if value not in ("", None, [])}


def filter_allowed(doc: dict[str, Any], allowed_fields: set[str]) -> dict[str, Any]:
    return {key: value for key, value in doc.items() if key in allowed_fields}


def first_non_group_value(client: ERPNextClient, doctype: str, preferred: str, fallback: str) -> str:
    records = client.list_docs(
        doctype,
        fields=["name", "is_group"],
        filters=[[doctype, "is_group", "=", 0]],
        limit=50,
    )
    for record in records:
        if record.get("name") == preferred:
            return preferred
    if records:
        return str(records[0]["name"])
    return fallback


def infer_city_state(area: str) -> tuple[str, str]:
    normalized = (area or "").lower()
    mapping = [
        ("new york", ("New York", "NY")),
        ("tampa", ("Tampa", "FL")),
        ("st. petersburg", ("St. Petersburg", "FL")),
        ("sarasota", ("Sarasota", "FL")),
        ("miami", ("Miami", "FL")),
        ("orlando", ("Orlando", "FL")),
        ("las vegas", ("Las Vegas", "NV")),
        ("los angeles", ("Los Angeles", "CA")),
        ("san francisco", ("San Francisco", "CA")),
        ("seattle", ("Seattle", "WA")),
        ("houston", ("Houston", "TX")),
        ("dallas", ("Dallas", "TX")),
        ("chicago", ("Chicago", "IL")),
        ("trenton", ("Trenton", "NJ")),
    ]
    for token, city_state in mapping:
        if token in normalized:
            return city_state
    return "Unknown", ""


def find_or_create_customer(client: ERPNextClient, row: SheetCallRow) -> str:
    customer_name, customer_type = parse_client_name(row.client_information, row.caller_phone, row.row_number)
    existing = client.find_one(
        "Customer",
        filters=[["Customer", "customer_name", "=", customer_name]],
        fields=["name", "customer_name"],
    )
    if existing:
        return str(existing["name"])

    customer_group = os.getenv("ERPNEXT_DEFAULT_CUSTOMER_GROUP") or first_non_group_value(
        client,
        "Customer Group",
        preferred="Commercial",
        fallback="Commercial",
    )
    territory = os.getenv("ERPNEXT_DEFAULT_TERRITORY") or first_non_group_value(
        client,
        "Territory",
        preferred="United States",
        fallback="United States",
    )

    doc = clean_doc(
        {
            "doctype": "Customer",
            "customer_name": customer_name,
            "customer_type": customer_type,
            "customer_group": customer_group,
            "territory": territory,
        }
    )
    return str(client.create_doc("Customer", doc).get("name") or customer_name)


def find_or_create_contact(client: ERPNextClient, row: SheetCallRow, customer_name: str) -> str:
    if row.email:
        existing = client.find_one(
            "Contact",
            filters=[["Contact", "email_id", "=", row.email]],
            fields=["name", "email_id"],
        )
        if existing:
            return str(existing["name"])

    if row.caller_phone:
        existing = client.find_one(
            "Contact",
            filters=[["Contact", "phone", "=", row.caller_phone]],
            fields=["name", "phone"],
        )
        if existing:
            return str(existing["name"])

    _customer_name, _customer_type, display_name = parse_client_identity(
        row.client_information,
        row.caller_phone,
        row.row_number,
    )
    first_name = display_name[:140] if display_name else f"Caller {row.row_number}"
    doc = clean_doc(
        {
            "doctype": "Contact",
            "first_name": first_name,
            "email_id": row.email,
            "phone": row.caller_phone,
            "links": [{"link_doctype": "Customer", "link_name": customer_name}],
            "phone_nos": [{"phone": row.caller_phone, "is_primary_phone": 1}] if row.caller_phone else [],
            "email_ids": [{"email_id": row.email, "is_primary": 1}] if row.email else [],
        }
    )
    return str(client.create_doc("Contact", doc).get("name") or first_name)


def find_or_create_address(client: ERPNextClient, row: SheetCallRow, customer_name: str) -> str:
    if not row.address:
        return ""
    city, state = infer_city_state(row.area)
    existing = client.find_one(
        "Address",
        filters=[["Address", "address_line1", "=", row.address]],
        fields=["name", "address_line1"],
    )
    if existing:
        return str(existing["name"])

    doc = clean_doc(
        {
            "doctype": "Address",
            "address_title": customer_name[:140],
            "address_type": "Billing",
            "address_line1": row.address,
            "city": city,
            "state": state,
            "country": "United States",
            "links": [{"link_doctype": "Customer", "link_name": customer_name}],
        }
    )
    return str(client.create_doc("Address", doc).get("name") or row.address)


def existing_repair_job_name(client: ERPNextClient, row: SheetCallRow) -> str | None:
    if row.recording_url:
        existing = client.find_one(
            "Repair Job",
            filters=[["Repair Job", "zadarma_recording_url", "=", row.recording_url]],
            fields=["name", "zadarma_recording_url"],
        )
        if existing:
            return str(existing["name"])
    if row.zadarma_call_id:
        existing = client.find_one(
            "Repair Job",
            filters=[["Repair Job", "zadarma_call_id", "=", row.zadarma_call_id]],
            fields=["name", "zadarma_call_id"],
        )
        if existing:
            return str(existing["name"])
    return None


def upsert_repair_job(
    client: ERPNextClient,
    row: SheetCallRow,
    customer_name: str,
    contact_name: str,
    address_name: str,
    *,
    allowed_fields: set[str],
) -> dict[str, Any]:
    internal_notes = [
        f"Imported from Google Sheet row {row.row_number}.",
        f"Original sheet status: {row.status or 'blank'}.",
    ]
    if row.comment:
        internal_notes.append(row.comment)
    if is_qualified_lead(row):
        internal_notes.append("Qualified lead candidate: yes.")
    else:
        internal_notes.append("Qualified lead candidate: no.")

    doc = clean_doc(
        {
            "doctype": "Repair Job",
            "naming_series": "RJ-.YYYY.-",
            "status": status_to_repair_status(row.status, row.service_summary),
            "customer": customer_name,
            "contact": contact_name,
            "service_address": address_name,
            "caller_phone": row.caller_phone,
            "business_phone_did": row.destination_number,
            "area": row.area,
            "marketing_source": row.source,
            "zadarma_recording_url": row.recording_url,
            "zadarma_call_id": row.zadarma_call_id,
            "call_datetime": row.call_datetime,
            "call_duration_seconds": row.duration_seconds,
            "call_transcript": row.transcript,
            "ai_call_summary": row.comment,
            "call_quality": row.call_quality,
            "purpose_of_call": row.purpose,
            "client_information_from_call": row.client_information,
            "service_summary": row.service_summary,
            "internal_comment": "\n".join(internal_notes),
        }
    )
    doc = filter_allowed(doc, allowed_fields)

    existing_name = existing_repair_job_name(client, row)
    result = client.create_or_update_doc("Repair Job", doc, existing_name=existing_name)
    return {
        "action": "update" if existing_name else "create",
        "repair_job": result.get("name") or existing_name,
        "payload": doc,
    }


def load_sheet_rows(call_sheet_bot: Any, call_bot_root: Path, max_rows: int) -> tuple[list[list[dict[str, str]]], SheetColumns, str]:
    load_env_file(call_bot_root / ".env", override=True)
    spreadsheet_url = os.environ["SPREADSHEET_URL"]
    spreadsheet_id, gid_from_url = call_sheet_bot.parse_spreadsheet_url(spreadsheet_url)
    sheet_gid = int(os.getenv("SHEET_GID") or gid_from_url or 0)
    sheets, _drive = call_sheet_bot.google_clients()
    sheet_title = call_sheet_bot.sheet_title_by_gid(sheets, spreadsheet_id, sheet_gid)
    rows = call_sheet_bot.read_sheet_grid(sheets, spreadsheet_id, sheet_title, max_rows)
    headers = [cell.get("text", "") for cell in rows[int(os.getenv("HEADER_ROW", "1")) - 1]]
    columns = detect_columns(call_sheet_bot, headers, rows)
    return rows, columns, sheet_title


def write_jsonl(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(data, ensure_ascii=False, default=str) + "\n")


def main() -> int:
    bypass_system_proxies()

    parser = argparse.ArgumentParser(description="Dry-run or execute Google Sheets/Zadarma rows into ERPNext Repair Job.")
    parser.add_argument("--call-bot-root", default=str(DEFAULT_CALL_BOT_ROOT))
    parser.add_argument("--row", type=int, help="1-based Google Sheet row number to ingest.")
    parser.add_argument("--call-id", help="Find and ingest the row with this Zadarma call ID.")
    parser.add_argument("--recording-url", help="Find and ingest the row with this exact recording URL.")
    parser.add_argument("--expect-call-id", help="Safety check: selected row must have this Zadarma call ID.")
    parser.add_argument("--expect-url", help="Safety check: selected row must have this exact recording URL.")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--max-rows", type=int, default=80)
    parser.add_argument("--execute", action="store_true", help="Actually write to ERPNext. Default is dry-run.")
    parser.add_argument("--allow-missing-transcript", action="store_true")
    parser.add_argument("--log-path", default=str(ROOT / "logs" / "ingest.jsonl"))
    args = parser.parse_args()

    call_bot_root = Path(args.call_bot_root).resolve()
    call_sheet_bot = load_call_bot_module(call_bot_root)
    rows, columns, sheet_title = load_sheet_rows(call_sheet_bot, call_bot_root, args.max_rows)

    config = ERPNextConfig.from_env()
    if args.execute:
        config = ERPNextConfig(
            base_url=config.base_url,
            api_key=config.api_key,
            api_secret=config.api_secret,
            company=config.company,
            dry_run=False,
            timeout_seconds=config.timeout_seconds,
            max_retries=config.max_retries,
            retry_wait_seconds=config.retry_wait_seconds,
        )
    client = ERPNextClient(config)
    allowed_fields = client.get_doctype_fields("Repair Job")

    print(f"ERPNext site: {config.base_url}")
    print(f"Sheet: {sheet_title}")
    print(f"Mode: {'EXECUTE' if args.execute else 'DRY RUN'}")
    print(f"Columns: {asdict(columns)}")

    body_start = int(os.getenv("HEADER_ROW", "1"))
    candidate_indexes: list[int] = []
    if args.execute and args.row and not (args.expect_call_id or args.expect_url):
        print("Refusing execute by row number without --expect-call-id or --expect-url because live Sheet rows can move.")
        return 2

    if args.row:
        candidate_indexes = [args.row - 1]
    elif args.call_id or args.recording_url:
        for row_index in range(body_start, len(rows)):
            recording_url = cell_url_or_text(call_sheet_bot, rows, row_index, columns.link)
            if args.recording_url and recording_url == args.recording_url:
                candidate_indexes = [row_index]
                break
            if args.call_id and zadarma_call_id_from_url(recording_url) == args.call_id:
                candidate_indexes = [row_index]
                break
    else:
        for row_index in range(body_start, len(rows)):
            recording_url = cell_url_or_text(call_sheet_bot, rows, row_index, columns.link)
            transcript = cell_text(call_sheet_bot, rows, row_index, columns.transcript)
            if not recording_url:
                continue
            if not transcript and not args.allow_missing_transcript:
                continue
            candidate_indexes.append(row_index)
            if len(candidate_indexes) >= args.limit:
                break

    if not candidate_indexes:
        print("No eligible rows found.")
        return 0

    for row_index in candidate_indexes:
        row = make_sheet_row(call_sheet_bot, rows, row_index, columns)
        if args.expect_url and row.recording_url != args.expect_url:
            print(f"Selected row {row.row_number} URL changed. Refusing to ingest.")
            print(f"Expected: {args.expect_url}")
            print(f"Actual:   {row.recording_url}")
            return 2
        if args.expect_call_id and row.zadarma_call_id != args.expect_call_id:
            print(f"Selected row {row.row_number} call ID changed. Refusing to ingest.")
            print(f"Expected: {args.expect_call_id}")
            print(f"Actual:   {row.zadarma_call_id}")
            return 2
        print(f"\nProcessing sheet row {row.row_number}: {row.recording_url}")

        customer_name = find_or_create_customer(client, row)
        contact_name = find_or_create_contact(client, row, customer_name)
        address_name = find_or_create_address(client, row, customer_name)
        repair_result = upsert_repair_job(
            client,
            row,
            customer_name,
            contact_name,
            address_name,
            allowed_fields=allowed_fields,
        )

        result = {
            "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "mode": "execute" if args.execute else "dry-run",
            "sheet_row": row.row_number,
            "qualified_lead": is_qualified_lead(row),
            "customer": customer_name,
            "contact": contact_name,
            "address": address_name,
            **repair_result,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        write_jsonl(Path(args.log_path), result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
