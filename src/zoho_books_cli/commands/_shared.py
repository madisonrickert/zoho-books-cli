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


def parse_query_pairs(pairs: list[str] | None) -> dict[str, str]:
    """Parse repeated `--query key=value` flags into a dict of strings.

    Values are kept verbatim as strings; no integer coercion.
    """
    result: dict[str, str] = {}
    for item in pairs or []:
        if "=" not in item:
            raise ValidationError(f"--query must be key=value, got: {item}")
        key, value = item.split("=", 1)
        if not key:
            raise ValidationError(f"--query key must be non-empty, got: {item}")
        result[key] = value
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
