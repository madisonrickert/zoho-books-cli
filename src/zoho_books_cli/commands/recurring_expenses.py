"""`zb recurring-expenses ...` — full coverage of /recurring-expenses.

Thin wrappers: CRUD + stop/resume + children/history. Stop and resume use PUT
per Zoho's API spec.
"""

from __future__ import annotations

import typer

from zoho_books_cli import config
from zoho_books_cli.client import ZohoBooksClient
from zoho_books_cli.commands import _shared

app = typer.Typer(
    help="Recurring expense operations (CRUD + stop/resume + children/history).",
    no_args_is_help=True,
)

BASE = "/recurringexpenses"


@app.command("list")
def list_recurring(
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
    """List recurring expenses. Returns one page plus page_context."""
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
            "recurring_expenses",
            page_all=page_all,
            page_limit=page_limit,
            page_delay_ms=page_delay,
        )


@app.command("create")
def create_recurring(
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Create a recurring expense."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(BASE, json_body=json_body)
    _shared.emit_object(resp)


@app.command("get")
def get_recurring(
    recurring_expense_id: str = typer.Argument(..., help="Zoho Books recurring_expense_id."),
):
    """Get a single recurring expense by ID."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"{BASE}/{recurring_expense_id}")
    _shared.emit_object(resp)


@app.command("update")
def update_recurring(
    recurring_expense_id: str = typer.Argument(..., help="Zoho Books recurring_expense_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Update a recurring expense by ID."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.put(f"{BASE}/{recurring_expense_id}", json_body=json_body)
    _shared.emit_object(resp)


@app.command("update-by-custom-field")
def update_recurring_by_custom_field(
    key: str = typer.Option(..., "--key", help="Custom-field API name."),
    value: str = typer.Option(..., "--value", help="Custom-field value to match on."),
    body: str = typer.Option(
        ..., "--body", "-b", help="JSON body with the update fields. IDs must be strings."
    ),
    upsert: bool = typer.Option(
        False, "--upsert", help="Create a new recurring expense if no match is found."
    ),
):
    """Update a recurring expense by a custom field's unique value.

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
def delete_recurring(
    recurring_expense_id: str = typer.Argument(..., help="Zoho Books recurring_expense_id."),
):
    """Delete a recurring expense by ID."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"{BASE}/{recurring_expense_id}")
    _shared.emit_action("recurring_expense_id", recurring_expense_id, resp)


@app.command("stop")
def stop_recurring(
    recurring_expense_id: str = typer.Argument(..., help="Zoho Books recurring_expense_id."),
):
    """Stop a recurring expense (POST /recurringexpenses/{id}/status/stop)."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{recurring_expense_id}/status/stop")
    _shared.emit_action("recurring_expense_id", recurring_expense_id, resp)


@app.command("resume")
def resume_recurring(
    recurring_expense_id: str = typer.Argument(..., help="Zoho Books recurring_expense_id."),
):
    """Resume a recurring expense (POST /recurringexpenses/{id}/status/resume)."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{recurring_expense_id}/status/resume")
    _shared.emit_action("recurring_expense_id", recurring_expense_id, resp)


@app.command("children")
def list_children(
    recurring_expense_id: str = typer.Argument(..., help="Zoho Books recurring_expense_id."),
    query: list[str] = typer.Option(None, "--query", "-q", help="Query params as key=value."),
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
    """List child expenses created from a recurring expense."""
    q = _shared.parse_query_pairs(query, params)
    if page is not None:
        q["page"] = str(page)
    if per_page is not None:
        q["per_page"] = str(per_page)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        _shared.emit_list_paginated(
            client,
            f"{BASE}/{recurring_expense_id}/expenses",
            q,
            "expenses",
            page_all=page_all,
            page_limit=page_limit,
            page_delay_ms=page_delay,
        )


@app.command("history")
def list_history(
    recurring_expense_id: str = typer.Argument(..., help="Zoho Books recurring_expense_id."),
):
    """List history / comments for a recurring expense."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"{BASE}/{recurring_expense_id}/comments")
    _shared.emit_list(resp, "comments")
