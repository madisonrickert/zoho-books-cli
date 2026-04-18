"""`zb customer-payments ...` — full coverage of /customerpayments.

Thin wrappers: CRUD + update-by-custom-field + refunds sub-app. The singular
`/customerpayment/{id}/customfields` endpoint and the collection-level bulk
DELETE are left to `zb raw`.
"""

from __future__ import annotations

import typer

from zoho_books_cli import config
from zoho_books_cli.client import ZohoBooksClient
from zoho_books_cli.commands import _shared

app = typer.Typer(
    help="Customer payment operations (CRUD + update-by-custom-field + refunds).",
    no_args_is_help=True,
)
refunds_app = typer.Typer(help="Refunds on a customer payment (CRUD).", no_args_is_help=True)
app.add_typer(refunds_app, name="refunds")

BASE = "/customerpayments"


@app.command("list")
def list_payments(
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
):
    """List customer payments. Returns one page plus page_context."""
    q = _shared.parse_query_pairs(query, params)
    if page is not None:
        q["page"] = str(page)
    if per_page is not None:
        q["per_page"] = str(per_page)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(BASE, query=q)
    _shared.emit_list(resp, "customerpayments")


@app.command("create")
def create_payment(
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Create a customer payment."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(BASE, json_body=json_body)
    _shared.emit_object(resp)


@app.command("get")
def get_payment(
    payment_id: str = typer.Argument(..., help="Zoho Books customer_payment_id."),
):
    """Get a single customer payment by ID."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"{BASE}/{payment_id}")
    _shared.emit_object(resp)


@app.command("update")
def update_payment(
    payment_id: str = typer.Argument(..., help="Zoho Books customer_payment_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Update a customer payment by ID."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.put(f"{BASE}/{payment_id}", json_body=json_body)
    _shared.emit_object(resp)


@app.command("update-by-custom-field")
def update_payment_by_custom_field(
    key: str = typer.Option(..., "--key", help="Custom-field API name."),
    value: str = typer.Option(..., "--value", help="Custom-field value to match on."),
    body: str = typer.Option(
        ..., "--body", "-b", help="JSON body with the update fields. IDs must be strings."
    ),
    upsert: bool = typer.Option(
        False, "--upsert", help="Create a new customer payment if no match is found."
    ),
):
    """Update a customer payment by a custom field's unique value.

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
def delete_payment(
    payment_id: str = typer.Argument(..., help="Zoho Books customer_payment_id."),
):
    """Delete a customer payment by ID."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"{BASE}/{payment_id}")
    _shared.emit_action("payment_id", payment_id, resp)


@refunds_app.command("list")
def list_refunds(
    payment_id: str = typer.Argument(..., help="Zoho Books customer_payment_id."),
    query: list[str] = typer.Option(None, "--query", "-q", help="Query params as key=value."),
    params: str = typer.Option(
        None,
        "--params",
        help="Query params as a JSON object. Merged on top of --query.",
    ),
    page: int = typer.Option(None, "--page", help="Page number (1-indexed)."),
    per_page: int = typer.Option(None, "--per-page", help="Rows per page."),
):
    """List refunds issued against a customer payment."""
    q = _shared.parse_query_pairs(query, params)
    if page is not None:
        q["page"] = str(page)
    if per_page is not None:
        q["per_page"] = str(per_page)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"{BASE}/{payment_id}/refunds", query=q)
    _shared.emit_list(resp, "payment_refunds")


@refunds_app.command("create")
def create_refund(
    payment_id: str = typer.Argument(..., help="Zoho Books customer_payment_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Issue a refund against a customer payment."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{payment_id}/refunds", json_body=json_body)
    _shared.emit_object(resp)


@refunds_app.command("get")
def get_refund(
    payment_id: str = typer.Argument(..., help="Zoho Books customer_payment_id."),
    refund_id: str = typer.Argument(..., help="Zoho Books refund_id."),
):
    """Get a single refund on a customer payment."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"{BASE}/{payment_id}/refunds/{refund_id}")
    _shared.emit_object(resp)


@refunds_app.command("update")
def update_refund(
    payment_id: str = typer.Argument(..., help="Zoho Books customer_payment_id."),
    refund_id: str = typer.Argument(..., help="Zoho Books refund_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Update a refund on a customer payment."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.put(f"{BASE}/{payment_id}/refunds/{refund_id}", json_body=json_body)
    _shared.emit_object(resp)


@refunds_app.command("delete")
def delete_refund(
    payment_id: str = typer.Argument(..., help="Zoho Books customer_payment_id."),
    refund_id: str = typer.Argument(..., help="Zoho Books refund_id."),
):
    """Delete a refund on a customer payment."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"{BASE}/{payment_id}/refunds/{refund_id}")
    _shared.emit_action("refund_id", refund_id, resp)
