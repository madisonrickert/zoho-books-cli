"""`zb invoices ...` — full coverage of /invoices.

Thin wrappers: CRUD + update-by-custom-field + state actions
(mark-sent / mark-void / mark-draft + write-off / cancel-write-off),
email, payment-reminder send, payments-applied (read-only), credits
sub-app (list / apply / delete), comments (list / add / delete),
documents (get / delete; no list — Zoho exposes per-document only),
attachments (add / get / delete), and template registry / apply.

Live-verified envelope keys against the user's Zoho org:
- /invoices               → invoices  (list)
- /invoices/{id}          → invoice   (single)
- /invoices/{id}/comments → comments
- /invoices/{id}/payments → payments
- /invoices/{id}/creditsapplied → credits
- /invoices/templates     → templates
"""

from __future__ import annotations

from pathlib import Path

import typer

from zoho_books_cli import _uploads, config, output
from zoho_books_cli.client import ZohoBooksClient
from zoho_books_cli.commands import _shared
from zoho_books_cli.errors import ZohoCLIError

app = typer.Typer(
    help=(
        "Invoice operations (CRUD + state + email + reminders + payments + "
        "credits + comments + documents + attachments + templates)."
    ),
    no_args_is_help=True,
)
attachments_app = typer.Typer(help="Manage attachments on an invoice.", no_args_is_help=True)
credits_app = typer.Typer(help="Credits applied to an invoice.", no_args_is_help=True)
comments_app = typer.Typer(help="Invoice comments (list / add / delete).", no_args_is_help=True)
documents_app = typer.Typer(help="Per-document operations on an invoice.", no_args_is_help=True)
templates_app = typer.Typer(help="Invoice PDF templates.", no_args_is_help=True)
payments_app = typer.Typer(help="Payments applied to an invoice (read-only).", no_args_is_help=True)
reminders_app = typer.Typer(help="Payment reminders for an invoice.", no_args_is_help=True)
app.add_typer(attachments_app, name="attachments")
app.add_typer(credits_app, name="credits")
app.add_typer(comments_app, name="comments")
app.add_typer(documents_app, name="documents")
app.add_typer(templates_app, name="templates")
app.add_typer(payments_app, name="payments")
app.add_typer(reminders_app, name="reminders")

BASE = "/invoices"


# --- top-level CRUD ----------------------------------------------------------


@app.command("list")
def list_invoices(
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
    """List invoices. Returns one page plus page_context."""
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
            "invoices",
            page_all=page_all,
            page_limit=page_limit,
            page_delay_ms=page_delay,
        )


@app.command("create")
def create_invoice(
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Create an invoice."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(BASE, json_body=json_body)
    _shared.emit_object(resp)


@app.command("get")
def get_invoice(
    invoice_id: str = typer.Argument(..., help="Zoho Books invoice_id."),
):
    """Get a single invoice by ID."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"{BASE}/{invoice_id}")
    _shared.emit_object(resp)


@app.command("update")
def update_invoice(
    invoice_id: str = typer.Argument(..., help="Zoho Books invoice_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Update an invoice by ID. Drop a line item by removing it from line_items."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.put(f"{BASE}/{invoice_id}", json_body=json_body)
    _shared.emit_object(resp)


@app.command("update-by-custom-field")
def update_invoice_by_custom_field(
    key: str = typer.Option(..., "--key", help="Custom-field API name."),
    value: str = typer.Option(..., "--value", help="Custom-field value to match on."),
    body: str = typer.Option(
        ..., "--body", "-b", help="JSON body with the update fields. IDs must be strings."
    ),
    upsert: bool = typer.Option(
        False, "--upsert", help="Create a new invoice if no match is found."
    ),
):
    """Update an invoice by a custom field's unique value.

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
def delete_invoice(
    invoice_id: str = typer.Argument(..., help="Zoho Books invoice_id."),
):
    """Delete an invoice. Invoices with payments/credits applied cannot be deleted."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"{BASE}/{invoice_id}")
    _shared.emit_action("invoice_id", invoice_id, resp)


# --- state actions -----------------------------------------------------------


@app.command("mark-sent")
def mark_sent(
    invoice_id: str = typer.Argument(..., help="Zoho Books invoice_id."),
):
    """Mark an invoice as sent (POST /invoices/{id}/status/sent)."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{invoice_id}/status/sent")
    _shared.emit_action("invoice_id", invoice_id, resp)


@app.command("mark-void")
def mark_void(
    invoice_id: str = typer.Argument(..., help="Zoho Books invoice_id."),
):
    """Mark an invoice as void (POST /invoices/{id}/status/void)."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{invoice_id}/status/void")
    _shared.emit_action("invoice_id", invoice_id, resp)


@app.command("mark-draft")
def mark_draft(
    invoice_id: str = typer.Argument(..., help="Zoho Books invoice_id."),
):
    """Mark an invoice as draft (POST /invoices/{id}/status/draft)."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{invoice_id}/status/draft")
    _shared.emit_action("invoice_id", invoice_id, resp)


@app.command("write-off")
def write_off(
    invoice_id: str = typer.Argument(..., help="Zoho Books invoice_id."),
):
    """Write off the outstanding amount on an invoice (POST /invoices/{id}/writeoff)."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{invoice_id}/writeoff")
    _shared.emit_action("invoice_id", invoice_id, resp)


@app.command("cancel-write-off")
def cancel_write_off(
    invoice_id: str = typer.Argument(..., help="Zoho Books invoice_id."),
):
    """Cancel a write-off (POST /invoices/{id}/writeoff/cancel)."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{invoice_id}/writeoff/cancel")
    _shared.emit_action("invoice_id", invoice_id, resp)


@app.command("email")
def email_invoice(
    invoice_id: str = typer.Argument(..., help="Zoho Books invoice_id."),
    body: str = typer.Option(
        None,
        "--body",
        "-b",
        help="Optional JSON body (to/cc/subject/body); empty body sends Zoho's default.",
    ),
):
    """Email an invoice (POST /invoices/{id}/email)."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{invoice_id}/email", json_body=json_body)
    _shared.emit_action("invoice_id", invoice_id, resp)


# --- reminders sub-app -------------------------------------------------------


@reminders_app.command("send")
def send_reminder(
    invoice_id: str = typer.Argument(..., help="Zoho Books invoice_id."),
    body: str = typer.Option(
        None,
        "--body",
        "-b",
        help="Optional JSON body (to/cc/subject/body); empty body sends Zoho's default.",
    ),
):
    """Send a payment reminder for an invoice (POST /invoices/{id}/paymentreminder)."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{invoice_id}/paymentreminder", json_body=json_body)
    _shared.emit_action("invoice_id", invoice_id, resp)


# --- payments sub-app (read-only) --------------------------------------------


@payments_app.command("list")
def list_payments(
    invoice_id: str = typer.Argument(..., help="Zoho Books invoice_id."),
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
    """List payments applied to an invoice (read-only).

    To record a new payment, use `zb customer-payments create` and reference
    the invoice via the body's `invoices[]` array — Zoho does not expose a
    direct POST under /invoices/{id}/payments.
    """
    q = _shared.parse_query_pairs(query, params)
    if page is not None:
        q["page"] = str(page)
    if per_page is not None:
        q["per_page"] = str(per_page)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        _shared.emit_list_paginated(
            client,
            f"{BASE}/{invoice_id}/payments",
            q,
            "payments",
            page_all=page_all,
            page_limit=page_limit,
            page_delay_ms=page_delay,
        )


# --- credits sub-app ---------------------------------------------------------


@credits_app.command("list")
def list_credits(
    invoice_id: str = typer.Argument(..., help="Zoho Books invoice_id."),
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
    """List credits applied to an invoice (GET /invoices/{id}/creditsapplied)."""
    q: dict[str, str] = {}
    if page is not None:
        q["page"] = str(page)
    if per_page is not None:
        q["per_page"] = str(per_page)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        _shared.emit_list_paginated(
            client,
            f"{BASE}/{invoice_id}/creditsapplied",
            q,
            "credits",
            page_all=page_all,
            page_limit=page_limit,
            page_delay_ms=page_delay,
        )


@credits_app.command("apply")
def apply_credits(
    invoice_id: str = typer.Argument(..., help="Zoho Books invoice_id."),
    body: str = typer.Option(
        ...,
        "--body",
        "-b",
        help=(
            "JSON body wrapping credit applications, e.g. "
            '{"apply_creditnotes":[{"creditnote_id":"...","amount_applied":100}],'
            '"apply_customerpayments":[{"payment_id":"...","amount_applied":50}]}. '
            "IDs must be strings."
        ),
    ),
):
    """Apply existing credits or unused payments to an invoice (POST /invoices/{id}/credits)."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{invoice_id}/credits", json_body=json_body)
    _shared.emit_object(resp)


@credits_app.command("delete")
def delete_credit(
    invoice_id: str = typer.Argument(..., help="Zoho Books invoice_id."),
    credit_id: str = typer.Argument(..., help="Applied-credit row id."),
):
    """Unapply a credit row from an invoice.

    Removes only the application row (the link between invoice and the credit
    note / customer-payment); the underlying credit-note / payment record is
    untouched and the released amount becomes available to apply elsewhere.
    """
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"{BASE}/{invoice_id}/creditsapplied/{credit_id}")
    _shared.emit_action("credit_id", credit_id, resp)


# --- comments sub-app --------------------------------------------------------


@comments_app.command("list")
def list_comments(
    invoice_id: str = typer.Argument(..., help="Zoho Books invoice_id."),
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
    """List recent activity and comments on an invoice."""
    q: dict[str, str] = {}
    if page is not None:
        q["page"] = str(page)
    if per_page is not None:
        q["per_page"] = str(per_page)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        _shared.emit_list_paginated(
            client,
            f"{BASE}/{invoice_id}/comments",
            q,
            "comments",
            page_all=page_all,
            page_limit=page_limit,
            page_delay_ms=page_delay,
        )


@comments_app.command("add")
def add_comment(
    invoice_id: str = typer.Argument(..., help="Zoho Books invoice_id."),
    body: str = typer.Option(
        ...,
        "--body",
        "-b",
        help='JSON body, e.g. {"description":"Spoke with vendor about NET-30."}.',
    ),
):
    """Post a comment to an invoice (POST /invoices/{id}/comments)."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{invoice_id}/comments", json_body=json_body)
    _shared.emit_object(resp)


@comments_app.command("delete")
def delete_comment(
    invoice_id: str = typer.Argument(..., help="Zoho Books invoice_id."),
    comment_id: str = typer.Argument(..., help="Zoho Books comment_id."),
):
    """Delete a comment on an invoice (DELETE /invoices/{id}/comments/{comment_id})."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"{BASE}/{invoice_id}/comments/{comment_id}")
    _shared.emit_action("comment_id", comment_id, resp)


# --- documents sub-app -------------------------------------------------------


@documents_app.command("get")
def get_document(
    invoice_id: str = typer.Argument(..., help="Zoho Books invoice_id."),
    document_id: str = typer.Argument(..., help="Zoho Books document_id."),
):
    """Get metadata for a specific document attached to an invoice.

    Zoho exposes per-document GET only — there is no documents-list endpoint.
    For binary download of the primary attachment, use `invoices attachments
    get`. For per-document metadata, supply the document_id directly (find it
    via the invoice payload's `documents[]` array).
    """
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"{BASE}/{invoice_id}/documents/{document_id}")
    _shared.emit_object(resp)


@documents_app.command("delete")
def delete_document(
    invoice_id: str = typer.Argument(..., help="Zoho Books invoice_id."),
    document_id: str = typer.Argument(..., help="Zoho Books document_id."),
):
    """Delete a document from an invoice. System-generated documents cannot be removed."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"{BASE}/{invoice_id}/documents/{document_id}")
    _shared.emit_action("document_id", document_id, resp)


# --- templates sub-app -------------------------------------------------------


@templates_app.command("list")
def list_templates(
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
    """List the org's invoice PDF templates (GET /invoices/templates)."""
    q: dict[str, str] = {}
    if page is not None:
        q["page"] = str(page)
    if per_page is not None:
        q["per_page"] = str(per_page)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        _shared.emit_list_paginated(
            client,
            f"{BASE}/templates",
            q,
            "templates",
            page_all=page_all,
            page_limit=page_limit,
            page_delay_ms=page_delay,
        )


@templates_app.command("apply")
def apply_template(
    invoice_id: str = typer.Argument(..., help="Zoho Books invoice_id."),
    template_id: str = typer.Argument(..., help="Zoho Books template_id."),
):
    """Apply a PDF template to an invoice (PUT /invoices/{id}/templates/{template_id})."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.put(f"{BASE}/{invoice_id}/templates/{template_id}")
    _shared.emit_action("invoice_id", invoice_id, resp)


# --- attachments sub-app -----------------------------------------------------


@attachments_app.command("add")
def attachments_add(
    invoice_id: str = typer.Argument(..., help="Zoho Books invoice_id."),
    files: list[Path] = typer.Argument(..., help="One or more files (≤10 MB each)."),
):
    """Attach one or more files to an invoice.

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
                    resp = client.post(f"{BASE}/{invoice_id}/attachment", files=multipart)
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
    output.emit_success({"invoice_id": invoice_id, "results": results})


@attachments_app.command("get")
def attachments_get(
    invoice_id: str = typer.Argument(..., help="Zoho Books invoice_id."),
    output_path: Path = typer.Option(
        ..., "--output", "-o", help="Path to write the downloaded attachment."
    ),
):
    """Download the file attached to an invoice."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        body, content_type = client.get_bytes(f"{BASE}/{invoice_id}/attachment")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(body)
    output.emit_success(
        {
            "invoice_id": invoice_id,
            "saved_to": str(output_path),
            "size_bytes": len(body),
            "content_type": content_type,
        }
    )


@attachments_app.command("delete")
def attachments_delete(
    invoice_id: str = typer.Argument(..., help="Zoho Books invoice_id."),
):
    """Delete attachments from an invoice."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"{BASE}/{invoice_id}/attachment")
    output.emit_success({"invoice_id": invoice_id, "deleted": True, "response": resp})
