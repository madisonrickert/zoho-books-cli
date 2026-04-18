"""`zb chart-of-accounts ...` — full coverage of /chartofaccounts.

Thin wrappers: CRUD + mark-active / mark-inactive + a `transactions` sub-app
(list + delete).
"""

from __future__ import annotations

import typer

from zoho_books_cli import config
from zoho_books_cli.client import ZohoBooksClient
from zoho_books_cli.commands import _shared

app = typer.Typer(
    help="Chart-of-accounts operations (CRUD + mark-active / mark-inactive + transactions).",
    no_args_is_help=True,
)
transactions_app = typer.Typer(
    help="Transactions posted to a chart-of-accounts account.", no_args_is_help=True
)
app.add_typer(transactions_app, name="transactions")

BASE = "/chartofaccounts"


@app.command("list")
def list_accounts(
    query: list[str] = typer.Option(
        None, "--query", "-q", help="Query params as key=value. May be repeated."
    ),
    page: int = typer.Option(None, "--page", help="Page number (1-indexed)."),
    per_page: int = typer.Option(None, "--per-page", help="Rows per page."),
):
    """List chart-of-accounts accounts. Returns one page plus page_context."""
    q = _shared.parse_query_pairs(query)
    if page is not None:
        q["page"] = str(page)
    if per_page is not None:
        q["per_page"] = str(per_page)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(BASE, query=q)
    _shared.emit_list(resp, "chartofaccounts")


@app.command("create")
def create_account(
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Create a chart-of-accounts account."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(BASE, json_body=json_body)
    _shared.emit_object(resp)


@app.command("get")
def get_account(
    account_id: str = typer.Argument(..., help="Zoho Books account_id."),
):
    """Get a single chart-of-accounts account by ID."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"{BASE}/{account_id}")
    _shared.emit_object(resp)


@app.command("update")
def update_account(
    account_id: str = typer.Argument(..., help="Zoho Books account_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Update a chart-of-accounts account by ID."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.put(f"{BASE}/{account_id}", json_body=json_body)
    _shared.emit_object(resp)


@app.command("delete")
def delete_account(
    account_id: str = typer.Argument(..., help="Zoho Books account_id."),
):
    """Delete a chart-of-accounts account by ID."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"{BASE}/{account_id}")
    _shared.emit_action("account_id", account_id, resp)


@app.command("mark-active")
def mark_active(
    account_id: str = typer.Argument(..., help="Zoho Books account_id."),
):
    """Mark an account as active (POST /chartofaccounts/{id}/active)."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{account_id}/active")
    _shared.emit_action("account_id", account_id, resp)


@app.command("mark-inactive")
def mark_inactive(
    account_id: str = typer.Argument(..., help="Zoho Books account_id."),
):
    """Mark an account as inactive (POST /chartofaccounts/{id}/inactive)."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{account_id}/inactive")
    _shared.emit_action("account_id", account_id, resp)


@transactions_app.command("list")
def list_transactions(
    query: list[str] = typer.Option(
        None, "--query", "-q", help="Query params as key=value. May be repeated."
    ),
    page: int = typer.Option(None, "--page", help="Page number (1-indexed)."),
    per_page: int = typer.Option(None, "--per-page", help="Rows per page."),
):
    """List transactions posted to chart-of-accounts accounts."""
    q = _shared.parse_query_pairs(query)
    if page is not None:
        q["page"] = str(page)
    if per_page is not None:
        q["per_page"] = str(per_page)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"{BASE}/transactions", query=q)
    _shared.emit_list(resp, "transactions")


@transactions_app.command("delete")
def delete_transaction(
    transaction_id: str = typer.Argument(..., help="Zoho Books transaction_id."),
):
    """Delete a manually-posted chart-of-accounts transaction."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"{BASE}/transactions/{transaction_id}")
    _shared.emit_action("transaction_id", transaction_id, resp)
