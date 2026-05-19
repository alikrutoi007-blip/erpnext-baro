from __future__ import annotations

import json
import http.client
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path | None = None) -> dict[str, str]:
    env_path = path or ROOT / ".env"
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def env_flag(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class ERPNextConfig:
    base_url: str
    api_key: str
    api_secret: str
    company: str = "Baro Service"
    dry_run: bool = True
    timeout_seconds: int = 180
    max_retries: int = 2
    retry_wait_seconds: int = 5

    @classmethod
    def from_env(cls) -> "ERPNextConfig":
        file_env = load_env()
        merged = {**file_env, **os.environ}
        base_url = merged.get("ERPNEXT_BASE_URL", "").rstrip("/")
        api_key = merged.get("ERPNEXT_API_KEY", "")
        api_secret = merged.get("ERPNEXT_API_SECRET", "")
        company = merged.get("ERPNEXT_COMPANY", "Baro Service")
        dry_run = env_flag(merged.get("ERPNEXT_DRY_RUN"), default=True)
        timeout_seconds = int(merged.get("ERPNEXT_TIMEOUT_SECONDS", "180"))
        max_retries = int(merged.get("ERPNEXT_MAX_RETRIES", "2"))
        retry_wait_seconds = int(merged.get("ERPNEXT_RETRY_WAIT_SECONDS", "5"))
        missing = [
            key
            for key, value in {
                "ERPNEXT_BASE_URL": base_url,
                "ERPNEXT_API_KEY": api_key,
                "ERPNEXT_API_SECRET": api_secret,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(f"Missing required ERPNext settings: {', '.join(missing)}")
        return cls(
            base_url=base_url,
            api_key=api_key,
            api_secret=api_secret,
            company=company,
            dry_run=dry_run,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            retry_wait_seconds=retry_wait_seconds,
        )


class ERPNextError(RuntimeError):
    pass


def truncate_error_body(body: str, limit: int = 1200) -> str:
    cleaned = " ".join(body.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "... [truncated]"


class ERPNextClient:
    def __init__(self, config: ERPNextConfig):
        self.config = config
        # Local Codex/Windows sessions can define dummy HTTP_PROXY values.
        # ERPNext lives on Tailscale/local network, so API calls must bypass proxies.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @property
    def auth_header(self) -> str:
        return f"token {self.config.api_key}:{self.config.api_secret}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        url = self.config.base_url + path
        if params:
            query = urllib.parse.urlencode(
                {
                    key: json.dumps(value) if isinstance(value, (dict, list)) else value
                    for key, value in params.items()
                }
            )
            url = f"{url}?{query}"

        body: bytes | None = None
        headers = {
            "Authorization": self.auth_header,
            "Accept": "application/json",
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        for attempt in range(self.config.max_retries + 1):
            try:
                with self._opener.open(req, timeout=self.config.timeout_seconds) as response:
                    raw = response.read().decode("utf-8")
                    if not raw:
                        return None
                    return json.loads(raw)
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace")
                if exc.code in {502, 503, 504} and attempt < self.config.max_retries:
                    time.sleep(self.config.retry_wait_seconds * (attempt + 1))
                    continue
                raise ERPNextError(
                    f"ERPNext HTTP {exc.code} for {method} {path}: {truncate_error_body(error_body)}"
                ) from exc
            except urllib.error.URLError as exc:
                if attempt < self.config.max_retries:
                    time.sleep(self.config.retry_wait_seconds * (attempt + 1))
                    continue
                raise ERPNextError(f"ERPNext connection failed for {method} {path}: {exc}") from exc
            except (http.client.HTTPException, ConnectionError) as exc:
                if attempt < self.config.max_retries:
                    time.sleep(self.config.retry_wait_seconds * (attempt + 1))
                    continue
                raise ERPNextError(f"ERPNext connection interrupted for {method} {path}: {exc}") from exc
            except TimeoutError as exc:
                if attempt < self.config.max_retries:
                    time.sleep(self.config.retry_wait_seconds * (attempt + 1))
                    continue
                raise ERPNextError(
                    f"ERPNext request timed out after {self.config.timeout_seconds}s for {method} {path}"
                ) from exc

        raise ERPNextError(f"ERPNext request failed for {method} {path}")

    def ping(self) -> str:
        data = self._request("GET", "/api/method/frappe.auth.get_logged_user")
        return str(data.get("message", ""))

    def list_docs(
        self,
        doctype: str,
        *,
        fields: list[str] | None = None,
        filters: list[Any] | dict[str, Any] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit_page_length": limit}
        if fields:
            params["fields"] = fields
        if filters:
            params["filters"] = filters
        data = self._request("GET", f"/api/resource/{urllib.parse.quote(doctype)}", params=params)
        return list(data.get("data", []))

    def get_doc(self, doctype: str, name: str) -> dict[str, Any]:
        data = self._request(
            "GET",
            f"/api/resource/{urllib.parse.quote(doctype)}/{urllib.parse.quote(name)}",
        )
        return dict(data.get("data", {}))

    def create_doc(self, doctype: str, doc: dict[str, Any]) -> dict[str, Any]:
        if self.config.dry_run:
            return {
                "dry_run": True,
                "doctype": doctype,
                "name": dry_run_name(doctype, doc),
                "data": doc,
            }
        data = self._request(
            "POST",
            f"/api/resource/{urllib.parse.quote(doctype)}",
            payload=doc,
        )
        return dict(data.get("data", {}))

    def update_doc(self, doctype: str, name: str, doc: dict[str, Any]) -> dict[str, Any]:
        if self.config.dry_run:
            return {"dry_run": True, "doctype": doctype, "name": name, "data": doc}
        data = self._request(
            "PUT",
            f"/api/resource/{urllib.parse.quote(doctype)}/{urllib.parse.quote(name)}",
            payload=doc,
        )
        return dict(data.get("data", {}))

    def find_by_field(self, doctype: str, fieldname: str, value: str, *, limit: int = 5) -> list[dict[str, Any]]:
        return self.list_docs(
            doctype,
            fields=["name", fieldname],
            filters=[[doctype, fieldname, "=", value]],
            limit=limit,
        )

    def find_one_by_field(self, doctype: str, fieldname: str, value: str) -> dict[str, Any] | None:
        matches = self.find_by_field(doctype, fieldname, value, limit=1)
        return matches[0] if matches else None

    def find_one(
        self,
        doctype: str,
        *,
        filters: list[Any] | dict[str, Any],
        fields: list[str] | None = None,
    ) -> dict[str, Any] | None:
        matches = self.list_docs(
            doctype,
            fields=fields or ["name"],
            filters=filters,
            limit=1,
        )
        return matches[0] if matches else None

    def create_or_update_doc(
        self,
        doctype: str,
        doc: dict[str, Any],
        *,
        existing_name: str | None,
    ) -> dict[str, Any]:
        if existing_name:
            return self.update_doc(doctype, existing_name, doc)
        return self.create_doc(doctype, doc)

    def get_doctype_fields(self, doctype: str) -> set[str]:
        doc = self.get_doc("DocType", doctype)
        fields = {"name", "doctype"}
        for field in doc.get("fields", []):
            fieldname = field.get("fieldname")
            if fieldname:
                fields.add(str(fieldname))
        return fields


def get_client() -> ERPNextClient:
    return ERPNextClient(ERPNextConfig.from_env())


def dry_run_name(doctype: str, doc: dict[str, Any]) -> str:
    for key in (
        "name",
        "label",
        "item_code",
        "employee_name",
        "customer_name",
        "project_name",
        "subject",
        "email_id",
        "phone",
        "remarks",
        "description",
        "zadarma_call_id",
        "zadarma_recording_url",
    ):
        value = doc.get(key)
        if value:
            return f"DRY-RUN-{doctype}-{value}"
    return f"DRY-RUN-{doctype}"
