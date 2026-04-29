"""`zb bills ...` — full coverage of /bills.

Thin wrappers: CRUD + update-by-custom-field + state actions
(mark-void / mark-open) + email + payments-applied sub-app +
comments (read-only) + attachments (add / get / delete).

The collection key used by Zoho is `bills` for list and `bill` for the
single-object envelope; envelope normalization is handled by
`_shared.emit_list_paginated` / `emit_object`.
"""

from __future__ import annotations

from pathlib import Path

import typer

from zoho_books_cli import _uploads, config, output
from zoho_books_cli.client import ZohoBooksClient
from zoho_books_cli.commands import _shared
from zoho_books_cli.errors import ZohoCLIError

app = typer.Typer(
    help="Bill operations (CRUD + state + email + payments + comments + attachments).",
    no_args_is_help=True,
)
attachments_app = typer.Typer(help="Manage attachments on a bill.", no_args_is_help=True)
payments_app = typer.Typer(help="Payments applied to a bill.", no_args_is_help=True)
comments_app = typer.Typer(help="Bill history and comments (read-only).", no_args_is_help=True)
app.add_typer(attachments_app, name="attachments")
app.add_typer(payments_app, name="payments")
app.add_typer(comments_app, name="comments")

BASE = "/bills"


@app.command("list")
def list_bills(
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
    """List bills. Returns one page plus page_context."""
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
            "bills",
            page_all=page_all,
            page_limit=page_limit,
            page_delay_ms=page_delay,
        )


@app.command("create")
def create_bill(
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Create a bill."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(BASE, json_body=json_body)
    _shared.emit_object(resp)


@app.command("get")
def get_bill(
    bill_id: str = typer.Argument(..., help="Zoho Books bill_id."),
):
    """Get a single bill by ID."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"{BASE}/{bill_id}")
    _shared.emit_object(resp)


@app.command("update")
def update_bill(
    bill_id: str = typer.Argument(..., help="Zoho Books bill_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Update a bill by ID."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.put(f"{BASE}/{bill_id}", json_body=json_body)
    _shared.emit_object(resp)


@app.command("update-by-custom-field")
def update_bill_by_custom_field(
    key: str = typer.Option(..., "--key", help="Custom-field API name."),
    value: str = typer.Option(..., "--value", help="Custom-field value to match on."),
    body: str = typer.Option(
        ..., "--body", "-b", help="JSON body with the update fields. IDs must be strings."
    ),
    upsert: bool = typer.Option(False, "--upsert", help="Create a new bill if no match is found."),
):
    """Update a bill by a custom field's unique value.

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
def delete_bill(
    bill_id: str = typer.Argument(..., help="Zoho Books bill_id."),
):
    """Delete a bill by ID."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"{BASE}/{bill_id}")
    _shared.emit_action("bill_id", bill_id, resp)


@app.command("mark-void")
def mark_void(
    bill_id: str = typer.Argument(..., help="Zoho Books bill_id."),
):
    """Mark a bill as void (POST /bills/{id}/status/void)."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{bill_id}/status/void")
    _shared.emit_action("bill_id", bill_id, resp)


@app.command("mark-open")
def mark_open(
    bill_id: str = typer.Argument(..., help="Zoho Books bill_id."),
):
    """Mark a bill as open (POST /bills/{id}/status/open)."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{bill_id}/status/open")
    _shared.emit_action("bill_id", bill_id, resp)


@app.command("email")
def email_bill(
    bill_id: str = typer.Argument(..., help="Zoho Books bill_id."),
    body: str = typer.Option(
        None,
        "--body",
        "-b",
        help="Optional JSON body (to/cc/subject/body); empty body sends Zoho's default.",
    ),
):
    """Email a bill (POST /bills/{id}/email)."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{bill_id}/email", json_body=json_body)
    _shared.emit_action("bill_id", bill_id, resp)


# --- payments sub-app --------------------------------------------------------


@payments_app.command("list")
def list_payments(
    bill_id: str = typer.Argument(..., help="Zoho Books bill_id."),
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
    """List payments applied to a bill."""
    q = _shared.parse_query_pairs(query, params)
    if page is not None:
        q["page"] = str(page)
    if per_page is not None:
        q["per_page"] = str(per_page)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        _shared.emit_list_paginated(
            client,
            f"{BASE}/{bill_id}/payments",
            q,
            "payments",
            page_all=page_all,
            page_limit=page_limit,
            page_delay_ms=page_delay,
        )


@payments_app.command("apply")
def apply_payment(
    bill_id: str = typer.Argument(..., help="Zoho Books bill_id."),
    body: str = typer.Option(
        ...,
        "--body",
        "-b",
        help=(
            'JSON body wrapping the application rows, e.g. {"bill_payments":'
            '[{"payment_id":"...","amount_applied":100}]}. IDs must be strings.'
        ),
    ),
):
    """Apply existing payments or vendor credits to a bill (POST /bills/{id}/payments).

    The endpoint applies pre-existing payment / vendor-credit records to this
    bill; it does not create new payment records. Use the customer-payments or
    `zb raw POST /vendorpayments` paths for record creation.
    """
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{bill_id}/payments", json_body=json_body)
    _shared.emit_object(resp)


@payments_app.command("delete")
def delete_payment(
    bill_id: str = typer.Argument(..., help="Zoho Books bill_id."),
    bill_payment_id: str = typer.Argument(..., help="Zoho Books bill_payment_id."),
):
    """Unapply a payment from a bill (DELETE /bills/{id}/payments/{bill_payment_id}).

    Removes only the application row that links this bill to the payment; the
    underlying payment record (vendor-payment / vendor-credit) is untouched and
    can be re-applied or applied to a different bill afterwards.
    """
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"{BASE}/{bill_id}/payments/{bill_payment_id}")
    _shared.emit_action("bill_payment_id", bill_payment_id, resp)


# --- comments sub-app --------------------------------------------------------


@comments_app.command("list")
def list_comments(
    bill_id: str = typer.Argument(..., help="Zoho Books bill_id."),
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
    """List recent activity and comments on a bill (read-only)."""
    q: dict[str, str] = {}
    if page is not None:
        q["page"] = str(page)
    if per_page is not None:
        q["per_page"] = str(per_page)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        _shared.emit_list_paginated(
            client,
            f"{BASE}/{bill_id}/comments",
            q,
            "comments",
            page_all=page_all,
            page_limit=page_limit,
            page_delay_ms=page_delay,
        )


# --- attachments sub-app -----------------------------------------------------


@attachments_app.command("add")
def attachments_add(
    bill_id: str = typer.Argument(..., help="Zoho Books bill_id."),
    files: list[Path] = typer.Argument(..., help="One or more files (≤10 MB each)."),
):
    """Attach one or more files to a bill.

    Partial failure is tolerated: each file is uploaded independently and the
    per-file outcome is returned in the result array.
    """
    cfg = config.load()
    results: list[dict] = []
    with ZohoBooksClient(cfg) as client:
        for file in files:
            entry: dict = {"file": str(file)}
            try:
                _uploads.validate(file)
                with file.open("rb") as fh:
                    multipart = {"attachment": (file.name, fh, _uploads.guess_mime(file))}
                    resp = client.post(f"{BASE}/{bill_id}/attachment", files=multipart)
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
    output.emit_success({"bill_id": bill_id, "results": results})


@attachments_app.command("get")
def attachments_get(
    bill_id: str = typer.Argument(..., help="Zoho Books bill_id."),
    output_path: Path = typer.Option(
        ..., "--output", "-o", help="Path to write the downloaded attachment."
    ),
):
    """Download the file attached to a bill."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        body, content_type = client.get_bytes(f"{BASE}/{bill_id}/attachment")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(body)
    output.emit_success(
        {
            "bill_id": bill_id,
            "saved_to": str(output_path),
            "size_bytes": len(body),
            "content_type": content_type,
        }
    )


@attachments_app.command("delete")
def attachments_delete(
    bill_id: str = typer.Argument(..., help="Zoho Books bill_id."),
):
    """Delete attachments from a bill."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"{BASE}/{bill_id}/attachment")
    output.emit_success({"bill_id": bill_id, "deleted": True, "response": resp})
