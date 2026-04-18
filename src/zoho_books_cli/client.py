"""Thin HTTPX wrapper around the Zoho Books REST API.

Handles:
  - Region → base URL
  - organization_id query-param injection
  - 401 → transparent refresh → retry once
  - 429 → honor Retry-After with exponential backoff
  - Typed exceptions mapped to CLI exit codes
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import typer

from zoho_books_cli import auth, config, output
from zoho_books_cli.config import RuntimeConfig
from zoho_books_cli.errors import (
    APIError,
    NetworkError,
    NotFound,
    RateLimited,
    ValidationError,
)

API_PREFIX = "/books/v3"
DEFAULT_TIMEOUT = 30.0
UPLOAD_TIMEOUT = 120.0
MAX_429_RETRIES = 3


class ZohoBooksClient:
    def __init__(self, cfg: RuntimeConfig, *, timeout: float = DEFAULT_TIMEOUT):
        self.cfg = cfg
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ZohoBooksClient:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # --- public verbs ---------------------------------------------------------

    def get(self, path: str, *, query: dict[str, Any] | None = None) -> Any:
        return self._request("GET", path, query=query)

    def get_bytes(
        self, path: str, *, query: dict[str, Any] | None = None
    ) -> tuple[bytes, str | None]:
        """GET an endpoint that returns raw bytes (e.g. receipt PDF download).

        Returns (body_bytes, content_type). Error responses (non-2xx) still raise
        the typed exceptions via `_parse_response` of the JSON-parsed error body.
        """
        return self._request("GET", path, query=query, _raw_bytes=True)

    def post(
        self,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        json_body: Any = None,
        files: dict[str, Any] | None = None,
    ) -> Any:
        return self._request("POST", path, query=query, json_body=json_body, files=files)

    def put(
        self,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        json_body: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        return self._request("PUT", path, query=query, json_body=json_body, headers=headers)

    def delete(self, path: str, *, query: dict[str, Any] | None = None) -> Any:
        return self._request("DELETE", path, query=query)

    # --- internals ------------------------------------------------------------

    def _ensure_access_token(self) -> str:
        """Return a valid access token, refreshing if expired or missing."""
        now = time.time()
        if self.cfg.access_token and self.cfg.expires_at and self.cfg.expires_at - 30 > now:
            return self.cfg.access_token
        return self._refresh()

    def _refresh(self) -> str:
        config.require_auth(self.cfg)
        body = auth.refresh_access_token(
            client_id=self.cfg.client_id,
            client_secret=self.cfg.client_secret,
            refresh_token=self.cfg.refresh_token,
            region=self.cfg.region,
        )
        access = body["access_token"]
        expires_at = time.time() + float(body.get("expires_in", 3600))
        self.cfg.access_token = access
        self.cfg.expires_at = expires_at
        config.update_access_token(access, expires_at)
        return access

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        json_body: Any = None,
        files: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        _refreshed: bool = False,
        _retry_count: int = 0,
        _raw_bytes: bool = False,
    ) -> Any:
        config.require_auth(self.cfg)
        if not self.cfg.org_id:
            raise ValidationError(
                "No organization_id configured. Run `zb org list` then `zb org use <id>`, "
                "or set ZOHO_ORG_ID."
            )

        url = self._build_url(path)
        params = {"organization_id": self.cfg.org_id, **(query or {})}

        if output.is_dry_run():
            files_preview = None
            if files:
                files_preview = {
                    field: {"filename": tup[0], "mime": tup[2]}
                    for field, tup in files.items()
                    if isinstance(tup, tuple) and len(tup) >= 3
                }
            output.emit_success(
                {
                    "dry_run": True,
                    "method": method,
                    "url": url,
                    "query": params,
                    "headers": dict(headers or {}),
                    "json_body": json_body,
                    "files": files_preview,
                }
            )
            raise typer.Exit(0)

        req_headers = {"Authorization": f"Zoho-oauthtoken {self._ensure_access_token()}"}
        if headers:
            req_headers.update(headers)
        timeout = UPLOAD_TIMEOUT if files else DEFAULT_TIMEOUT

        try:
            resp = self._client.request(
                method,
                url,
                params=params,
                json=json_body if files is None else None,
                files=files,
                headers=req_headers,
                timeout=timeout,
            )
        except httpx.TimeoutException as e:
            raise NetworkError(f"Request timed out: {e}") from e
        except httpx.RequestError as e:
            raise NetworkError(f"Network error: {e}") from e

        if resp.status_code == 401 and not _refreshed:
            # token may have been revoked or expired early
            self._refresh()
            return self._request(
                method,
                path,
                query=query,
                json_body=json_body,
                files=files,
                headers=headers,
                _refreshed=True,
                _retry_count=_retry_count,
                _raw_bytes=_raw_bytes,
            )

        if resp.status_code == 429:
            if _retry_count >= MAX_429_RETRIES:
                retry_after = _parse_retry_after(resp)
                raise RateLimited(
                    "Rate limit exceeded; retries exhausted.",
                    {"retry_after_s": retry_after, "max_retries": MAX_429_RETRIES},
                )
            delay = _parse_retry_after(resp) or min(2**_retry_count, 30)
            time.sleep(delay)
            return self._request(
                method,
                path,
                query=query,
                json_body=json_body,
                files=files,
                headers=headers,
                _refreshed=_refreshed,
                _retry_count=_retry_count + 1,
                _raw_bytes=_raw_bytes,
            )

        if _raw_bytes and resp.is_success:
            return resp.content, resp.headers.get("content-type")
        return _parse_response(resp)

    def _build_url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        if path.startswith(API_PREFIX):
            return f"{self.cfg.region.api_url}{path}"
        return f"{self.cfg.region.api_url}{API_PREFIX}{path}"


def _parse_retry_after(resp: httpx.Response) -> int:
    raw = resp.headers.get("Retry-After")
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError:
        return 0


def _parse_response(resp: httpx.Response) -> Any:
    try:
        body = resp.json()
    except ValueError:
        body = resp.text

    if resp.is_success:
        return body

    if resp.status_code == 404:
        raise NotFound(
            _message_from_body(body, default="Resource not found."),
            {"http_status": 404, "body": body},
        )

    raise APIError(
        _message_from_body(body, default=f"Zoho API returned {resp.status_code}."),
        {
            "http_status": resp.status_code,
            "zoho_code": body.get("code") if isinstance(body, dict) else None,
            "body": body,
        },
    )


def _message_from_body(body: Any, *, default: str) -> str:
    if isinstance(body, dict):
        msg = body.get("message")
        if isinstance(msg, str) and msg:
            return msg
    return default
