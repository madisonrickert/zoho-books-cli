"""`zb expenses ...` — full coverage of /expenses plus receipt and attachment uploads.

The CRUD, list, and comments commands are thin wrappers: each takes `--body`
(inline JSON or `@file.json`) and repeatable `--query key=value`. The receipt
and attachments subtrees handle local binary uploads — the original MCP gap
that motivated this CLI.
"""

from __future__ import annotations

from pathlib import Path

import typer

from zoho_books_cli import _uploads, config, output
from zoho_books_cli.client import ZohoBooksClient
from zoho_books_cli.commands import _shared
from zoho_books_cli.errors import ZohoCLIError

app = typer.Typer(help="Expense operations (CRUD + receipts + attachments).", no_args_is_help=True)
receipt_app = typer.Typer(help="Single-image receipt per expense.", no_args_is_help=True)
attachments_app = typer.Typer(
    help="Multiple supplementary attachments per expense.", no_args_is_help=True
)
comments_app = typer.Typer(help="Expense history and comments (read-only).", no_args_is_help=True)
app.add_typer(receipt_app, name="receipt")
app.add_typer(attachments_app, name="attachments")
app.add_typer(comments_app, name="comments")


@app.command("list")
def list_expenses(
    query: list[str] = typer.Option(
        None, "--query", "-q", help="Query params as key=value. May be repeated."
    ),
    page: int = typer.Option(None, "--page", help="Page number (1-indexed)."),
    per_page: int = typer.Option(None, "--per-page", help="Rows per page."),
):
    """List expenses. Returns one page plus page_context."""
    q = _shared.parse_query_pairs(query)
    if page is not None:
        q["page"] = str(page)
    if per_page is not None:
        q["per_page"] = str(per_page)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get("/expenses", query=q)
    _shared.emit_list(resp, "expenses")


@app.command("create")
def create_expense(
    body: str = typer.Option(
        ...,
        "--body",
        "-b",
        help="JSON body. Either a literal string or @path/to/file.json. IDs must be strings.",
    ),
):
    """Create an expense. See Zoho Books API docs for the full field list."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post("/expenses", json_body=json_body)
    _shared.emit_object(resp)


@app.command("get")
def get_expense(
    expense_id: str = typer.Argument(..., help="Zoho Books expense_id."),
):
    """Get a single expense by ID."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"/expenses/{expense_id}")
    _shared.emit_object(resp)


@app.command("update")
def update_expense(
    expense_id: str = typer.Argument(..., help="Zoho Books expense_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Update an expense by ID."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.put(f"/expenses/{expense_id}", json_body=json_body)
    _shared.emit_object(resp)


@app.command("update-by-custom-field")
def update_expense_by_custom_field(
    key: str = typer.Option(..., "--key", help="Custom-field API name (e.g. cf_external_id)."),
    value: str = typer.Option(..., "--value", help="Custom-field value to match on."),
    body: str = typer.Option(
        ..., "--body", "-b", help="JSON body with the update fields. IDs must be strings."
    ),
    upsert: bool = typer.Option(
        False, "--upsert", help="Create a new expense if no match is found."
    ),
):
    """Update an expense by a custom field's unique value.

    Identifier is sent via X-Unique-Identifier-Key / X-Unique-Identifier-Value headers
    per Zoho's spec; the request body carries only the fields to update.
    """
    json_body = _shared.parse_body(body)
    headers = {"X-Unique-Identifier-Key": key, "X-Unique-Identifier-Value": value}
    if upsert:
        headers["X-Upsert"] = "true"
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.put("/expenses", json_body=json_body, headers=headers)
    _shared.emit_object(resp)


@app.command("delete")
def delete_expense(
    expense_id: str = typer.Argument(..., help="Zoho Books expense_id."),
):
    """Delete an expense by ID."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"/expenses/{expense_id}")
    _shared.emit_action("expense_id", expense_id, resp)


@comments_app.command("list")
def list_comments(
    expense_id: str = typer.Argument(..., help="Zoho Books expense_id."),
):
    """List history and comments for an expense (read-only)."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"/expenses/{expense_id}/comments")
    _shared.emit_list(resp, "comments")


@receipt_app.command("upload")
def receipt_upload(
    expense_id: str = typer.Argument(..., help="Zoho Books expense_id."),
    file: Path = typer.Argument(..., help="Path to a PDF, JPG, JPEG, PNG, or GIF (≤10 MB)."),
):
    """Upload a receipt to an expense. Replaces any existing receipt."""
    _uploads.validate(file)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client, file.open("rb") as fh:
        files = {"receipt": (file.name, fh, _uploads.guess_mime(file))}
        resp = client.post(f"/expenses/{expense_id}/receipt", files=files)
    output.emit_success(
        {
            "expense_id": expense_id,
            "uploaded": file.name,
            "size_bytes": file.stat().st_size,
            "response": resp,
        }
    )


@receipt_app.command("get")
def receipt_get(
    expense_id: str = typer.Argument(..., help="Zoho Books expense_id."),
    output_path: Path = typer.Option(
        ..., "--output", "-o", help="Path to write the downloaded receipt file."
    ),
):
    """Download the receipt file attached to an expense."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        body, content_type = client.get_bytes(f"/expenses/{expense_id}/receipt")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(body)
    output.emit_success(
        {
            "expense_id": expense_id,
            "saved_to": str(output_path),
            "size_bytes": len(body),
            "content_type": content_type,
        }
    )


@receipt_app.command("delete")
def receipt_delete(
    expense_id: str = typer.Argument(..., help="Zoho Books expense_id."),
):
    """Delete the receipt attached to an expense."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"/expenses/{expense_id}/receipt")
    output.emit_success({"expense_id": expense_id, "deleted": True, "response": resp})


@attachments_app.command("add")
def attachments_add(
    expense_id: str = typer.Argument(..., help="Zoho Books expense_id."),
    files: list[Path] = typer.Argument(
        ..., help="One or more files (PDF, JPG, JPEG, PNG, GIF; ≤10 MB each)."
    ),
):
    """Attach one or more supplementary files to an expense.

    Partial failure is tolerated: each file is uploaded independently and the
    per-file outcome is returned in the result array.
    """
    cfg = config.load()
    results: list[dict] = []
    with ZohoBooksClient(cfg) as client:
        for file in files:
            entry: dict = {"file": str(file)}
            try:
                _uploads.validate(file)
                with file.open("rb") as fh:
                    multipart = {"attachment": (file.name, fh, _uploads.guess_mime(file))}
                    resp = client.post(f"/expenses/{expense_id}/attachment", files=multipart)
                entry["ok"] = True
                entry["response"] = resp
            except ZohoCLIError as e:
                entry["ok"] = False
                entry["error"] = {
                    "code": e.code,
                    "message": e.message,
                    "details": e.details,
                }
            results.append(entry)
    output.emit_success({"expense_id": expense_id, "results": results})


@attachments_app.command("delete")
def attachments_delete(
    expense_id: str = typer.Argument(..., help="Zoho Books expense_id."),
):
    """Delete all attachments from an expense (Zoho exposes this as a single call)."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"/expenses/{expense_id}/attachment")
    output.emit_success({"expense_id": expense_id, "deleted": True, "response": resp})
