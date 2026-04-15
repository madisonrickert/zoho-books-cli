"""`zb expenses ...` — receipt and attachment operations.

These are the **headline features** of this CLI: uploading local binary files
and tagging them to a specific expense. The MCP server can't pass local file
bytes cleanly; this CLI can.
"""

from __future__ import annotations

from pathlib import Path

import typer

from zoho_books_cli import _uploads, config, output
from zoho_books_cli.client import ZohoBooksClient
from zoho_books_cli.errors import ZohoCLIError

app = typer.Typer(help="Expense receipt and attachment operations.", no_args_is_help=True)
receipt_app = typer.Typer(help="Single-image receipt per expense.", no_args_is_help=True)
attachments_app = typer.Typer(
    help="Multiple supplementary attachments per expense.", no_args_is_help=True
)
app.add_typer(receipt_app, name="receipt")
app.add_typer(attachments_app, name="attachments")


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
