"""`zb raw` — escape hatch for any Zoho Books endpoint."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from zoho_books_cli import _uploads, config, output
from zoho_books_cli.client import ZohoBooksClient
from zoho_books_cli.errors import ValidationError


def raw(
    method: str = typer.Argument(..., help="HTTP method: GET, POST, PUT, DELETE."),
    path: str = typer.Argument(..., help="Path under /books/v3 (leading slash optional)."),
    query: list[str] = typer.Option(
        None,
        "--query",
        "-q",
        help="Query params as key=value. May be repeated.",
    ),
    body: str = typer.Option(
        None,
        "--body",
        "-b",
        help="JSON body. Either a literal string or @path/to/file.json.",
    ),
    file: list[str] = typer.Option(
        None,
        "--file",
        "-f",
        help="Multipart file upload as field=path. May be repeated.",
    ),
):
    """Call any Zoho Books v3 endpoint directly.

    Authentication and organization_id are injected automatically.
    """
    method_u = method.upper()
    if method_u not in {"GET", "POST", "PUT", "DELETE"}:
        raise ValidationError(f"Unsupported method: {method}")

    q = _parse_kv_list(query, "--query")

    json_body = None
    if body:
        if body.startswith("@"):
            p = Path(body[1:])
            if not p.exists():
                raise ValidationError(f"Body file not found: {p}")
            json_body = json.loads(p.read_text(encoding="utf-8"))
        else:
            try:
                json_body = json.loads(body)
            except json.JSONDecodeError as e:
                raise ValidationError(f"--body is not valid JSON: {e}") from e

    files = None
    open_handles: list = []
    if file:
        files = {}
        for spec in file:
            if "=" not in spec:
                raise ValidationError(f"--file must be field=path, got: {spec}")
            field, path_str = spec.split("=", 1)
            fp = Path(path_str)
            _uploads.validate(fp)
            fh = fp.open("rb")
            open_handles.append(fh)
            files[field] = (fp.name, fh, _uploads.guess_mime(fp))

    cfg = config.load()
    try:
        with ZohoBooksClient(cfg) as client:
            if method_u == "GET":
                resp = client.get(path, query=q)
            elif method_u == "POST":
                resp = client.post(path, query=q, json_body=json_body, files=files)
            elif method_u == "PUT":
                resp = client.put(path, query=q, json_body=json_body)
            else:  # DELETE
                resp = client.delete(path, query=q)
    finally:
        for fh in open_handles:
            fh.close()

    output.emit_success({"method": method_u, "path": path, "response": resp})


def _parse_kv_list(items: list[str] | None, flag: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items or []:
        if "=" not in item:
            raise ValidationError(f"{flag} must be key=value, got: {item}")
        k, v = item.split("=", 1)
        result[k] = v
    return result
