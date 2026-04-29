"""`zb recurring-invoices ...` — full coverage of /recurringinvoices.

Thin wrappers: CRUD + update-by-custom-field + stop/resume + history (comments,
read-only) + per-recurring template apply. To list child invoices spawned
from a recurring invoice, filter the main invoices listing:
    zb invoices list --query recurring_invoice_id=<id>
Zoho does not expose a dedicated /recurringinvoices/{id}/childinvoices endpoint
(verified live: 404).
"""

from __future__ import annotations

import typer

from zoho_books_cli import config
from zoho_books_cli.client import ZohoBooksClient
from zoho_books_cli.commands import _shared

app = typer.Typer(
    help="Recurring invoice operations (CRUD + stop/resume + history + templates).",
    no_args_is_help=True,
)
templates_app = typer.Typer(help="Per-recurring-invoice template assignment.", no_args_is_help=True)
app.add_typer(templates_app, name="templates")

BASE = "/recurringinvoices"


@app.command("list")
def list_recurring_invoices(
    query: list[str] = typer.Option(
        None, "--query", "-q", help="Query params as key=value. May be repeated."
    ),
    params: str = typer.Option(
        None,
        "--params",
        help="Query params as a JSON object. Merged on top of --query.",
    ),
    page: int = typer.Option(None, "--page", help="Page number (1-indexed)."),
    per_page: int = typer.Option(None, "--per-page", help="Rows per page."),
    page_all: bool = typer.Option(
        False, "--page-all", help="Auto-paginate (NDJSON: one page per line)."
    ),
    page_limit: int = typer.Option(10, "--page-limit", help="Max pages with --page-all."),
    page_delay: int = typer.Option(
        100, "--page-delay", help="Delay between pages in ms with --page-all."
    ),
):
    """List recurring invoices. Returns one page plus page_context."""
    q = _shared.parse_query_pairs(query, params)
    if page is not None:
        q["page"] = str(page)
    if per_page is not None:
        q["per_page"] = str(per_page)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        _shared.emit_list_paginated(
            client,
            BASE,
            q,
            "recurring_invoices",
            page_all=page_all,
            page_limit=page_limit,
            page_delay_ms=page_delay,
        )


@app.command("create")
def create_recurring_invoice(
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Create a recurring invoice."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(BASE, json_body=json_body)
    _shared.emit_object(resp)


@app.command("get")
def get_recurring_invoice(
    recurring_invoice_id: str = typer.Argument(..., help="Zoho Books recurring_invoice_id."),
):
    """Get a single recurring invoice by ID."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"{BASE}/{recurring_invoice_id}")
    _shared.emit_object(resp)


@app.command("update")
def update_recurring_invoice(
    recurring_invoice_id: str = typer.Argument(..., help="Zoho Books recurring_invoice_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Update a recurring invoice by ID."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.put(f"{BASE}/{recurring_invoice_id}", json_body=json_body)
    _shared.emit_object(resp)


@app.command("update-by-custom-field")
def update_by_custom_field(
    key: str = typer.Option(..., "--key", help="Custom-field API name."),
    value: str = typer.Option(..., "--value", help="Custom-field value to match on."),
    body: str = typer.Option(
        ..., "--body", "-b", help="JSON body with the update fields. IDs must be strings."
    ),
    upsert: bool = typer.Option(
        False, "--upsert", help="Create a new recurring invoice if no match is found."
    ),
):
    """Update a recurring invoice by a custom field's unique value.

    Identifier is sent via X-Unique-Identifier-Key / X-Unique-Identifier-Value headers
    per Zoho's spec; the request body carries only the fields to update.
    """
    json_body = _shared.parse_body(body)
    headers = {"X-Unique-Identifier-Key": key, "X-Unique-Identifier-Value": value}
    if upsert:
        headers["X-Upsert"] = "true"
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.put(BASE, json_body=json_body, headers=headers)
    _shared.emit_object(resp)


@app.command("delete")
def delete_recurring_invoice(
    recurring_invoice_id: str = typer.Argument(..., help="Zoho Books recurring_invoice_id."),
):
    """Delete a recurring invoice by ID."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"{BASE}/{recurring_invoice_id}")
    _shared.emit_action("recurring_invoice_id", recurring_invoice_id, resp)


@app.command("stop")
def stop(
    recurring_invoice_id: str = typer.Argument(..., help="Zoho Books recurring_invoice_id."),
):
    """Stop a recurring invoice (POST /recurringinvoices/{id}/status/stop)."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{recurring_invoice_id}/status/stop")
    _shared.emit_action("recurring_invoice_id", recurring_invoice_id, resp)


@app.command("resume")
def resume(
    recurring_invoice_id: str = typer.Argument(..., help="Zoho Books recurring_invoice_id."),
):
    """Resume a stopped recurring invoice (POST /recurringinvoices/{id}/status/resume)."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{recurring_invoice_id}/status/resume")
    _shared.emit_action("recurring_invoice_id", recurring_invoice_id, resp)


@app.command("history")
def list_history(
    recurring_invoice_id: str = typer.Argument(..., help="Zoho Books recurring_invoice_id."),
):
    """List history / comments for a recurring invoice (read-only)."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"{BASE}/{recurring_invoice_id}/comments")
    _shared.emit_list(resp, "comments")


@templates_app.command("apply")
def apply_template(
    recurring_invoice_id: str = typer.Argument(..., help="Zoho Books recurring_invoice_id."),
    template_id: str = typer.Argument(..., help="Zoho Books template_id."),
):
    """Apply a PDF template to a recurring invoice.

    PUT /recurringinvoices/{id}/templates/{template_id}.
    """
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.put(f"{BASE}/{recurring_invoice_id}/templates/{template_id}")
    _shared.emit_action("recurring_invoice_id", recurring_invoice_id, resp)
