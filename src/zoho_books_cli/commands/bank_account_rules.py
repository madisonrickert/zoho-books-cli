"""`zb bank-rules ...` — full coverage of /bankaccounts/rules.

Bank rules automate categorization of imported transactions for a given bank or
credit-card account. The list endpoint requires `account_id` as a query
parameter; pass it via `--query account_id=...` or `--params '{"account_id":"..."}'`.
Thin wrappers: CRUD only — Zoho exposes nothing else on this resource.
"""

from __future__ import annotations

import typer

from zoho_books_cli import config
from zoho_books_cli.client import ZohoBooksClient
from zoho_books_cli.commands import _shared

app = typer.Typer(
    help="Bank account rule operations (CRUD).",
    no_args_is_help=True,
)

BASE = "/bankaccounts/rules"


@app.command("list")
def list_rules(
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
    """List bank rules. Requires `account_id` query param per Zoho's API."""
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
            "rules",
            page_all=page_all,
            page_limit=page_limit,
            page_delay_ms=page_delay,
        )


@app.command("get")
def get_rule(
    rule_id: str = typer.Argument(..., help="Zoho Books rule_id."),
):
    """Get a single bank rule by ID."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"{BASE}/{rule_id}")
    _shared.emit_object(resp)


@app.command("create")
def create_rule(
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Create a bank rule."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(BASE, json_body=json_body)
    _shared.emit_object(resp)


@app.command("update")
def update_rule(
    rule_id: str = typer.Argument(..., help="Zoho Books rule_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Update a bank rule by ID."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.put(f"{BASE}/{rule_id}", json_body=json_body)
    _shared.emit_object(resp)


@app.command("delete")
def delete_rule(
    rule_id: str = typer.Argument(..., help="Zoho Books rule_id."),
):
    """Delete a bank rule by ID."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"{BASE}/{rule_id}")
    _shared.emit_action("rule_id", rule_id, resp)
