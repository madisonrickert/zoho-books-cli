"""`zb projects ...` — CRUD + state actions + clone + invoices.

Thin wrappers: CRUD + update-by-custom-field + mark-active / mark-inactive /
clone + read-only invoices list. Sub-collections (users, tasks, comments) are
left to `zb raw` until real usage signal appears.
"""

from __future__ import annotations

import typer

from zoho_books_cli import config
from zoho_books_cli.client import ZohoBooksClient
from zoho_books_cli.commands import _shared

app = typer.Typer(
    help="Project operations (CRUD + clone + mark-active / mark-inactive + invoices).",
    no_args_is_help=True,
)

BASE = "/projects"


@app.command("list")
def list_projects(
    query: list[str] = typer.Option(
        None, "--query", "-q", help="Query params as key=value. May be repeated."
    ),
    page: int = typer.Option(None, "--page", help="Page number (1-indexed)."),
    per_page: int = typer.Option(None, "--per-page", help="Rows per page."),
):
    """List projects. Returns one page plus page_context."""
    q = _shared.parse_query_pairs(query)
    if page is not None:
        q["page"] = str(page)
    if per_page is not None:
        q["per_page"] = str(per_page)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(BASE, query=q)
    _shared.emit_list(resp, "projects")


@app.command("create")
def create_project(
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Create a project."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(BASE, json_body=json_body)
    _shared.emit_object(resp)


@app.command("get")
def get_project(
    project_id: str = typer.Argument(..., help="Zoho Books project_id."),
):
    """Get a single project by ID."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"{BASE}/{project_id}")
    _shared.emit_object(resp)


@app.command("update")
def update_project(
    project_id: str = typer.Argument(..., help="Zoho Books project_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Update a project by ID."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.put(f"{BASE}/{project_id}", json_body=json_body)
    _shared.emit_object(resp)


@app.command("update-by-custom-field")
def update_project_by_custom_field(
    key: str = typer.Option(..., "--key", help="Custom-field API name."),
    value: str = typer.Option(..., "--value", help="Custom-field value to match on."),
    body: str = typer.Option(
        ..., "--body", "-b", help="JSON body with the update fields. IDs must be strings."
    ),
    upsert: bool = typer.Option(
        False, "--upsert", help="Create a new project if no match is found."
    ),
):
    """Update a project by a custom field's unique value.

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
def delete_project(
    project_id: str = typer.Argument(..., help="Zoho Books project_id."),
):
    """Delete a project by ID."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"{BASE}/{project_id}")
    _shared.emit_action("project_id", project_id, resp)


@app.command("mark-active")
def mark_active(
    project_id: str = typer.Argument(..., help="Zoho Books project_id."),
):
    """Mark a project as active (POST /projects/{id}/active)."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{project_id}/active")
    _shared.emit_action("project_id", project_id, resp)


@app.command("mark-inactive")
def mark_inactive(
    project_id: str = typer.Argument(..., help="Zoho Books project_id."),
):
    """Mark a project as inactive (POST /projects/{id}/inactive)."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{project_id}/inactive")
    _shared.emit_action("project_id", project_id, resp)


@app.command("clone")
def clone_project(
    project_id: str = typer.Argument(..., help="Source Zoho Books project_id."),
    body: str = typer.Option(
        None,
        "--body",
        "-b",
        help="Optional JSON body with overrides (project_name, customer_id, ...). IDs must be strings.",
    ),
):
    """Clone a project (POST /projects/{id}/clone)."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{project_id}/clone", json_body=json_body)
    _shared.emit_object(resp)


@app.command("invoices")
def list_invoices(
    project_id: str = typer.Argument(..., help="Zoho Books project_id."),
    query: list[str] = typer.Option(None, "--query", "-q", help="Query params as key=value."),
    page: int = typer.Option(None, "--page", help="Page number (1-indexed)."),
    per_page: int = typer.Option(None, "--per-page", help="Rows per page."),
):
    """List invoices associated with a project (GET /projects/{id}/invoices)."""
    q = _shared.parse_query_pairs(query)
    if page is not None:
        q["page"] = str(page)
    if per_page is not None:
        q["per_page"] = str(per_page)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"{BASE}/{project_id}/invoices", query=q)
    _shared.emit_list(resp, "invoices")
