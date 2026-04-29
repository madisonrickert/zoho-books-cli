"""`zb contacts ...` — CRUD + search + state actions + comments + addresses + persons.

Thin wrappers: top-level CRUD + update-by-custom-field + search (name-contains
shortcut) + mark-active / mark-inactive + comments (read-only) + addresses
sub-app (CRUD over additional shipping/billing addresses) + persons sub-app
(CRUD over contact persons). The 1099 tracking, portal/reminder toggles, and
statement-email endpoints remain on `zb raw` until real usage signal appears.

Live-verified envelope keys:
- /contacts                            → contacts / contact
- /contacts/{id}/address               → addresses
- /contacts/contactpersons             → contact_persons / contact_person
"""

from __future__ import annotations

import typer

from zoho_books_cli import config
from zoho_books_cli.client import ZohoBooksClient
from zoho_books_cli.commands import _shared

app = typer.Typer(
    help=(
        "Contact operations (CRUD + search + mark-active / mark-inactive + "
        "comments + addresses + persons)."
    ),
    no_args_is_help=True,
)
addresses_app = typer.Typer(
    help="Additional addresses on a contact (list / add / update / delete).",
    no_args_is_help=True,
)
persons_app = typer.Typer(
    help=(
        "Contact persons (CRUD + mark-primary). The resource lives under "
        "/contacts/contactpersons (top-level), filtered by contact_id."
    ),
    no_args_is_help=True,
)
app.add_typer(addresses_app, name="addresses")
app.add_typer(persons_app, name="persons")

BASE = "/contacts"


@app.command("list")
def list_contacts(
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
    """List contacts. Returns one page plus page_context."""
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
            "contacts",
            page_all=page_all,
            page_limit=page_limit,
            page_delay_ms=page_delay,
        )


@app.command("search")
def search_contacts(
    term: str = typer.Argument(..., help="Substring to match on contact_name."),
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
    """Search contacts by name substring (GET /contacts?contact_name_contains=...)."""
    q: dict[str, str] = {"contact_name_contains": term}
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
            "contacts",
            page_all=page_all,
            page_limit=page_limit,
            page_delay_ms=page_delay,
        )


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
    page_all: bool = typer.Option(
        False, "--page-all", help="Auto-paginate (NDJSON: one page per line)."
    ),
    page_limit: int = typer.Option(10, "--page-limit", help="Max pages with --page-all."),
    page_delay: int = typer.Option(
        100, "--page-delay", help="Delay between pages in ms with --page-all."
    ),
):
    """List recent activity and comments on a contact (read-only)."""
    q: dict[str, str] = {}
    if page is not None:
        q["page"] = str(page)
    if per_page is not None:
        q["per_page"] = str(per_page)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        _shared.emit_list_paginated(
            client,
            f"{BASE}/{contact_id}/comments",
            q,
            "comments",
            page_all=page_all,
            page_limit=page_limit,
            page_delay_ms=page_delay,
        )


# --- addresses sub-app -------------------------------------------------------


@addresses_app.command("list")
def addresses_list(
    contact_id: str = typer.Argument(..., help="Zoho Books contact_id."),
):
    """List the contact's additional addresses (GET /contacts/{id}/address)."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"{BASE}/{contact_id}/address")
    _shared.emit_list(resp, "addresses")


@addresses_app.command("add")
def addresses_add(
    contact_id: str = typer.Argument(..., help="Zoho Books contact_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Add an additional address to a contact (POST /contacts/{id}/address)."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{contact_id}/address", json_body=json_body)
    _shared.emit_object(resp)


@addresses_app.command("update")
def addresses_update(
    contact_id: str = typer.Argument(..., help="Zoho Books contact_id."),
    address_id: str = typer.Argument(..., help="Zoho Books address_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Edit one of a contact's additional addresses (PUT /contacts/{id}/address/{address_id})."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.put(f"{BASE}/{contact_id}/address/{address_id}", json_body=json_body)
    _shared.emit_object(resp)


@addresses_app.command("delete")
def addresses_delete(
    contact_id: str = typer.Argument(..., help="Zoho Books contact_id."),
    address_id: str = typer.Argument(..., help="Zoho Books address_id."),
):
    """Delete an additional address (DELETE /contacts/{id}/address/{address_id})."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"{BASE}/{contact_id}/address/{address_id}")
    _shared.emit_action("address_id", address_id, resp)


# --- contact persons sub-app -------------------------------------------------


@persons_app.command("list")
def persons_list(
    contact_id: str = typer.Argument(..., help="Zoho Books contact_id (required by Zoho)."),
    query: list[str] = typer.Option(
        None, "--query", "-q", help="Extra query params as key=value. May be repeated."
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
    """List contact persons attached to a contact.

    Zoho's /contacts/contactpersons endpoint requires a contact_id filter; the
    CLI accepts it as a positional argument and injects it into the query so
    agents can't accidentally drop it.
    """
    q = _shared.parse_query_pairs(query, params)
    q["contact_id"] = contact_id
    if page is not None:
        q["page"] = str(page)
    if per_page is not None:
        q["per_page"] = str(per_page)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        _shared.emit_list_paginated(
            client,
            f"{BASE}/contactpersons",
            q,
            "contact_persons",
            page_all=page_all,
            page_limit=page_limit,
            page_delay_ms=page_delay,
        )


@persons_app.command("get")
def persons_get(
    contact_person_id: str = typer.Argument(..., help="Zoho Books contact_person_id."),
):
    """Get a single contact person by ID."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"{BASE}/contactpersons/{contact_person_id}")
    _shared.emit_object(resp)


@persons_app.command("create")
def persons_create(
    body: str = typer.Option(
        ...,
        "--body",
        "-b",
        help="JSON body, must include contact_id. IDs must be strings.",
    ),
):
    """Create a contact person (POST /contacts/contactpersons)."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/contactpersons", json_body=json_body)
    _shared.emit_object(resp)


@persons_app.command("update")
def persons_update(
    contact_person_id: str = typer.Argument(..., help="Zoho Books contact_person_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Update a contact person."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.put(f"{BASE}/contactpersons/{contact_person_id}", json_body=json_body)
    _shared.emit_object(resp)


@persons_app.command("delete")
def persons_delete(
    contact_person_id: str = typer.Argument(..., help="Zoho Books contact_person_id."),
):
    """Delete a contact person."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"{BASE}/contactpersons/{contact_person_id}")
    _shared.emit_action("contact_person_id", contact_person_id, resp)


@persons_app.command("mark-primary")
def persons_mark_primary(
    contact_person_id: str = typer.Argument(..., help="Zoho Books contact_person_id."),
):
    """Mark a contact person as the primary contact for their contact record.

    POST /contacts/contactpersons/{contact_person_id}/primary.
    """
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/contactpersons/{contact_person_id}/primary")
    _shared.emit_action("contact_person_id", contact_person_id, resp)
