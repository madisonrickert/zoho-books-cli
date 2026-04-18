"""`zb contacts ...` — CRUD + search + state actions + comments.

Thin wrappers: CRUD + update-by-custom-field + search (name-contains shortcut)
+ mark-active / mark-inactive + comments read. Contact persons, addresses,
refunds, 1099 tracking, portal/reminder toggles, and statement emails are left
to `zb raw` until real usage signal appears.
"""

from __future__ import annotations

import typer

from zoho_books_cli import config
from zoho_books_cli.client import ZohoBooksClient
from zoho_books_cli.commands import _shared

app = typer.Typer(
    help="Contact operations (CRUD + search + mark-active / mark-inactive + comments).",
    no_args_is_help=True,
)

BASE = "/contacts"


@app.command("list")
def list_contacts(
    query: list[str] = typer.Option(
        None, "--query", "-q", help="Query params as key=value. May be repeated."
    ),
    page: int = typer.Option(None, "--page", help="Page number (1-indexed)."),
    per_page: int = typer.Option(None, "--per-page", help="Rows per page."),
):
    """List contacts. Returns one page plus page_context."""
    q = _shared.parse_query_pairs(query)
    if page is not None:
        q["page"] = str(page)
    if per_page is not None:
        q["per_page"] = str(per_page)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(BASE, query=q)
    _shared.emit_list(resp, "contacts")


@app.command("search")
def search_contacts(
    term: str = typer.Argument(..., help="Substring to match on contact_name."),
    page: int = typer.Option(None, "--page", help="Page number (1-indexed)."),
    per_page: int = typer.Option(None, "--per-page", help="Rows per page."),
):
    """Search contacts by name substring (GET /contacts?contact_name_contains=...)."""
    q: dict[str, str] = {"contact_name_contains": term}
    if page is not None:
        q["page"] = str(page)
    if per_page is not None:
        q["per_page"] = str(per_page)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(BASE, query=q)
    _shared.emit_list(resp, "contacts")


@app.command("create")
def create_contact(
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Create a contact."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(BASE, json_body=json_body)
    _shared.emit_object(resp)


@app.command("get")
def get_contact(
    contact_id: str = typer.Argument(..., help="Zoho Books contact_id."),
):
    """Get a single contact by ID."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"{BASE}/{contact_id}")
    _shared.emit_object(resp)


@app.command("update")
def update_contact(
    contact_id: str = typer.Argument(..., help="Zoho Books contact_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Update a contact by ID."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.put(f"{BASE}/{contact_id}", json_body=json_body)
    _shared.emit_object(resp)


@app.command("update-by-custom-field")
def update_contact_by_custom_field(
    key: str = typer.Option(..., "--key", help="Custom-field API name."),
    value: str = typer.Option(..., "--value", help="Custom-field value to match on."),
    body: str = typer.Option(
        ..., "--body", "-b", help="JSON body with the update fields. IDs must be strings."
    ),
    upsert: bool = typer.Option(
        False, "--upsert", help="Create a new contact if no match is found."
    ),
):
    """Update a contact by a custom field's unique value.

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
def delete_contact(
    contact_id: str = typer.Argument(..., help="Zoho Books contact_id."),
):
    """Delete a contact by ID."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"{BASE}/{contact_id}")
    _shared.emit_action("contact_id", contact_id, resp)


@app.command("mark-active")
def mark_active(
    contact_id: str = typer.Argument(..., help="Zoho Books contact_id."),
):
    """Mark a contact as active (POST /contacts/{id}/active)."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{contact_id}/active")
    _shared.emit_action("contact_id", contact_id, resp)


@app.command("mark-inactive")
def mark_inactive(
    contact_id: str = typer.Argument(..., help="Zoho Books contact_id."),
):
    """Mark a contact as inactive (POST /contacts/{id}/inactive)."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{contact_id}/inactive")
    _shared.emit_action("contact_id", contact_id, resp)


@app.command("comments")
def list_comments(
    contact_id: str = typer.Argument(..., help="Zoho Books contact_id."),
    page: int = typer.Option(None, "--page", help="Page number (1-indexed)."),
    per_page: int = typer.Option(None, "--per-page", help="Rows per page."),
):
    """List recent activity and comments on a contact (read-only)."""
    q: dict[str, str] = {}
    if page is not None:
        q["page"] = str(page)
    if per_page is not None:
        q["per_page"] = str(per_page)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"{BASE}/{contact_id}/comments", query=q)
    _shared.emit_list(resp, "comments")
