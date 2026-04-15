"""`zb invoices attachments ...` — upload binary files to invoices."""

from __future__ import annotations

from pathlib import Path

import typer

from zoho_books_cli import _uploads, config, output
from zoho_books_cli.client import ZohoBooksClient
from zoho_books_cli.errors import ZohoCLIError

app = typer.Typer(help="Invoice attachment operations.", no_args_is_help=True)
attachments_app = typer.Typer(help="Manage attachments on an invoice.", no_args_is_help=True)
app.add_typer(attachments_app, name="attachments")


@attachments_app.command("add")
def attachments_add(
    invoice_id: str = typer.Argument(..., help="Zoho Books invoice_id."),
    files: list[Path] = typer.Argument(..., help="One or more files (≤10 MB each)."),
):
    """Attach one or more files to an invoice."""
    cfg = config.load()
    results: list[dict] = []
    with ZohoBooksClient(cfg) as client:
        for file in files:
            entry: dict = {"file": str(file)}
            try:
                _uploads.validate(file)
                with file.open("rb") as fh:
                    multipart = {"attachment": (file.name, fh, _uploads.guess_mime(file))}
                    resp = client.post(f"/invoices/{invoice_id}/attachment", files=multipart)
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
    output.emit_success({"invoice_id": invoice_id, "results": results})


@attachments_app.command("delete")
def attachments_delete(
    invoice_id: str = typer.Argument(..., help="Zoho Books invoice_id."),
):
    """Delete attachments from an invoice."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"/invoices/{invoice_id}/attachment")
    output.emit_success({"invoice_id": invoice_id, "deleted": True, "response": resp})
