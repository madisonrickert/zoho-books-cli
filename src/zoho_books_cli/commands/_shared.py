"""Shared helpers for thin-wrapper command modules.

The CLI never coerces ID-shaped values to Python ints beyond what `json.loads`
would do naturally; Python ints are arbitrary precision, so a 19-digit Zoho ID
round-trips through parse → dict → httpx → wire JSON without precision loss.
Query param values are preserved as strings, and Zoho response bodies are
passed through verbatim. See AGENTS.md for the consumer-side contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from zoho_books_cli import output
from zoho_books_cli.errors import ValidationError


def parse_body(raw: str | None) -> Any:
    """Parse the `--body` flag. Returns the decoded JSON value or None.

    Accepts either a literal JSON string or `@path/to/file.json`.
    """
    if raw is None or raw == "":
        return None
    if raw.startswith("@"):
        path = Path(raw[1:])
        if not path.exists():
            raise ValidationError(f"Body file not found: {path}")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValidationError(f"Body file is not valid JSON: {e}") from e
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValidationError(f"--body is not valid JSON: {e}") from e


def parse_query_pairs(
    pairs: list[str] | None, params_json: str | None = None
) -> dict[str, str]:
    """Parse repeated `--query key=value` flags plus optional `--params <JSON>`.

    Merge order: `--query` pairs first, then `--params` JSON on top, so that
    passing an explicit JSON object is treated as a deliberate override.
    Values are coerced to strings (Zoho expects query params as strings); no
    integer round-trip is introduced.
    """
    result: dict[str, str] = {}
    for item in pairs or []:
        if "=" not in item:
            raise ValidationError(f"--query must be key=value, got: {item}")
        key, value = item.split("=", 1)
        if not key:
            raise ValidationError(f"--query key must be non-empty, got: {item}")
        result[key] = value
    if params_json:
        try:
            parsed = json.loads(params_json)
        except json.JSONDecodeError as e:
            raise ValidationError(f"--params is not valid JSON: {e}") from e
        if not isinstance(parsed, dict):
            raise ValidationError(
                f"--params must be a JSON object (got {type(parsed).__name__})."
            )
        for key, value in parsed.items():
            if value is None:
                result.pop(key, None)
            elif isinstance(value, bool):
                result[key] = "true" if value else "false"
            else:
                result[key] = str(value)
    return result


def emit_list(resp: Any, collection_key: str) -> None:
    """Emit a Zoho list response as `{items, page_context}`.

    Strips Zoho's envelope `code`/`message` fields. If the collection key isn't
    present in the response (unusual — e.g. empty body), emits an empty list.
    """
    if not isinstance(resp, dict):
        output.emit_success({"items": [], "page_context": {}, "response": resp})
        return
    items = resp.get(collection_key, [])
    page_context = resp.get("page_context", {})
    output.emit_success({"items": items, "page_context": page_context})


def emit_list_paginated(
    client: Any,
    path: str,
    query: dict[str, str],
    collection_key: str,
    *,
    page_all: bool = False,
    page_limit: int = 10,
    page_delay_ms: int = 100,
) -> None:
    """Single-page passthrough by default; opt-in NDJSON auto-pagination.

    When `page_all` is False (default), behaves like `client.get(...) →
    emit_list(resp, collection_key)` — one JSON object, single page. This
    preserves the existing agent contract.

    When `page_all` is True, loops page=1,2,... up to `page_limit` or until
    Zoho's `page_context.has_more_page` is false, whichever comes first. Each
    page is emitted as its own JSON line (NDJSON) with the normal envelope, so
    streaming consumers can process pages incrementally. Sleeps
    `page_delay_ms` between requests to stay under rate limits.

    Honors any existing `page` and `per_page` already set in the `query` dict
    — `--page N --page-all` starts the sweep at N instead of 1.
    """
    if not page_all:
        resp = client.get(path, query=query)
        emit_list(resp, collection_key)
        return

    import time

    q = dict(query)
    start = int(q.get("page", "1"))
    pages_fetched = 0
    current = start
    while pages_fetched < page_limit:
        q["page"] = str(current)
        resp = client.get(path, query=q)
        if isinstance(resp, dict):
            items = resp.get(collection_key, [])
            page_ctx = resp.get("page_context", {})
        else:
            items = []
            page_ctx = {}
        output.emit_success({"items": items, "page_context": page_ctx})
        pages_fetched += 1
        if not page_ctx.get("has_more_page"):
            break
        if page_delay_ms > 0:
            time.sleep(page_delay_ms / 1000.0)
        current += 1


def emit_object(resp: Any) -> None:
    """Emit a Zoho single-object response verbatim, stripping the envelope."""
    if not isinstance(resp, dict):
        output.emit_success({"response": resp})
        return
    stripped = {k: v for k, v in resp.items() if k not in {"code", "message"}}
    output.emit_success(stripped)


def emit_action(id_field: str, id_value: str, resp: Any) -> None:
    """Emit an action response (no meaningful body) as `{<id_field>, acted, response}`."""
    output.emit_success({id_field: id_value, "acted": True, "response": resp})
