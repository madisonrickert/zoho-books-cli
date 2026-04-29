"""`zb projects ...` — CRUD + state + clone + invoices + users + tasks + comments.

Thin wrappers: top-level CRUD + update-by-custom-field + mark-active /
mark-inactive / clone + read-only invoices list, plus three sub-apps:
- `users`    : list / get / add / invite / update / delete
- `tasks`    : list / get / add / update / delete
- `comments` : list / add / delete

Live-verified envelope keys against the user's Zoho org:
- /projects/{id}/users    → users (no page_context — flat list)
- /projects/{id}/tasks    → task (singular!) + page_context
- /projects/{id}/comments → comments + page_context
"""

from __future__ import annotations

import typer

from zoho_books_cli import config
from zoho_books_cli.client import ZohoBooksClient
from zoho_books_cli.commands import _shared

app = typer.Typer(
    help=(
        "Project operations (CRUD + clone + mark-active / mark-inactive + invoices + "
        "users + tasks + comments)."
    ),
    no_args_is_help=True,
)
users_app = typer.Typer(
    help="Project users (list / get / add / invite / update / delete).", no_args_is_help=True
)
tasks_app = typer.Typer(
    help="Project tasks (list / get / add / update / delete).", no_args_is_help=True
)
comments_app = typer.Typer(help="Project comments (list / add / delete).", no_args_is_help=True)
app.add_typer(users_app, name="users")
app.add_typer(tasks_app, name="tasks")
app.add_typer(comments_app, name="comments")

BASE = "/projects"


@app.command("list")
def list_projects(
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
    """List projects. Returns one page plus page_context."""
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
            "projects",
            page_all=page_all,
            page_limit=page_limit,
            page_delay_ms=page_delay,
        )


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
    """List invoices associated with a project (GET /projects/{id}/invoices)."""
    q = _shared.parse_query_pairs(query, params)
    if page is not None:
        q["page"] = str(page)
    if per_page is not None:
        q["per_page"] = str(per_page)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        _shared.emit_list_paginated(
            client,
            f"{BASE}/{project_id}/invoices",
            q,
            "invoices",
            page_all=page_all,
            page_limit=page_limit,
            page_delay_ms=page_delay,
        )


# --- users sub-app -----------------------------------------------------------


@users_app.command("list")
def users_list(
    project_id: str = typer.Argument(..., help="Zoho Books project_id."),
):
    """List users assigned to a project (GET /projects/{id}/users).

    Returns a flat list — Zoho does not paginate this resource.
    """
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"{BASE}/{project_id}/users")
    _shared.emit_list(resp, "users")


@users_app.command("get")
def users_get(
    project_id: str = typer.Argument(..., help="Zoho Books project_id."),
    user_id: str = typer.Argument(..., help="Zoho Books user_id."),
):
    """Get details of a project user."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"{BASE}/{project_id}/users/{user_id}")
    _shared.emit_object(resp)


@users_app.command("add")
def users_add(
    project_id: str = typer.Argument(..., help="Zoho Books project_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Assign one or more existing users to a project (POST /projects/{id}/users)."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{project_id}/users", json_body=json_body)
    _shared.emit_object(resp)


@users_app.command("invite")
def users_invite(
    project_id: str = typer.Argument(..., help="Zoho Books project_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Invite a new user to a project (POST /projects/{id}/users/invite)."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{project_id}/users/invite", json_body=json_body)
    _shared.emit_object(resp)


@users_app.command("update")
def users_update(
    project_id: str = typer.Argument(..., help="Zoho Books project_id."),
    user_id: str = typer.Argument(..., help="Zoho Books user_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Update a project user (PUT /projects/{id}/users/{user_id})."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.put(f"{BASE}/{project_id}/users/{user_id}", json_body=json_body)
    _shared.emit_object(resp)


@users_app.command("delete")
def users_delete(
    project_id: str = typer.Argument(..., help="Zoho Books project_id."),
    user_id: str = typer.Argument(..., help="Zoho Books user_id."),
):
    """Remove a user from a project (DELETE /projects/{id}/users/{user_id})."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"{BASE}/{project_id}/users/{user_id}")
    _shared.emit_action("user_id", user_id, resp)


# --- tasks sub-app -----------------------------------------------------------


@tasks_app.command("list")
def tasks_list(
    project_id: str = typer.Argument(..., help="Zoho Books project_id."),
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
    """List tasks attached to a project. Note Zoho's response key is the singular `task`."""
    q = _shared.parse_query_pairs(query, params)
    if page is not None:
        q["page"] = str(page)
    if per_page is not None:
        q["per_page"] = str(per_page)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        _shared.emit_list_paginated(
            client,
            f"{BASE}/{project_id}/tasks",
            q,
            "task",
            page_all=page_all,
            page_limit=page_limit,
            page_delay_ms=page_delay,
        )


@tasks_app.command("get")
def tasks_get(
    project_id: str = typer.Argument(..., help="Zoho Books project_id."),
    task_id: str = typer.Argument(..., help="Zoho Books task_id."),
):
    """Get a project task."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"{BASE}/{project_id}/tasks/{task_id}")
    _shared.emit_object(resp)


@tasks_app.command("add")
def tasks_add(
    project_id: str = typer.Argument(..., help="Zoho Books project_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Add a task to a project (POST /projects/{id}/tasks)."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{project_id}/tasks", json_body=json_body)
    _shared.emit_object(resp)


@tasks_app.command("update")
def tasks_update(
    project_id: str = typer.Argument(..., help="Zoho Books project_id."),
    task_id: str = typer.Argument(..., help="Zoho Books task_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Update a project task (PUT /projects/{id}/tasks/{task_id})."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.put(f"{BASE}/{project_id}/tasks/{task_id}", json_body=json_body)
    _shared.emit_object(resp)


@tasks_app.command("delete")
def tasks_delete(
    project_id: str = typer.Argument(..., help="Zoho Books project_id."),
    task_id: str = typer.Argument(..., help="Zoho Books task_id."),
):
    """Delete a project task (DELETE /projects/{id}/tasks/{task_id})."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"{BASE}/{project_id}/tasks/{task_id}")
    _shared.emit_action("task_id", task_id, resp)


# --- comments sub-app --------------------------------------------------------


@comments_app.command("list")
def comments_list(
    project_id: str = typer.Argument(..., help="Zoho Books project_id."),
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
    """List comments on a project."""
    q: dict[str, str] = {}
    if page is not None:
        q["page"] = str(page)
    if per_page is not None:
        q["per_page"] = str(per_page)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        _shared.emit_list_paginated(
            client,
            f"{BASE}/{project_id}/comments",
            q,
            "comments",
            page_all=page_all,
            page_limit=page_limit,
            page_delay_ms=page_delay,
        )


@comments_app.command("add")
def comments_add(
    project_id: str = typer.Argument(..., help="Zoho Books project_id."),
    body: str = typer.Option(
        ...,
        "--body",
        "-b",
        help='JSON body, e.g. {"description":"Spec finalized"}.',
    ),
):
    """Post a comment to a project (POST /projects/{id}/comments)."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{project_id}/comments", json_body=json_body)
    _shared.emit_object(resp)


@comments_app.command("delete")
def comments_delete(
    project_id: str = typer.Argument(..., help="Zoho Books project_id."),
    comment_id: str = typer.Argument(..., help="Zoho Books comment_id."),
):
    """Delete a comment from a project (DELETE /projects/{id}/comments/{comment_id})."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"{BASE}/{project_id}/comments/{comment_id}")
    _shared.emit_action("comment_id", comment_id, resp)
