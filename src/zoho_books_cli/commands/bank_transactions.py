"""`zb bank-transactions ...` — full coverage of /banktransactions.

Thin wrappers: CRUD, action verbs (match/unmatch/exclude/restore/uncategorize),
an 8-variant categorize sub-app, and the /banktransactions/bulk/statement
import subtree.

Several action verbs sit under /banktransactions/uncategorized/{id}/... per
Zoho's API layout; `unmatch` and `uncategorize` sit directly under
/banktransactions/{id}/... despite the naming asymmetry.
"""

from __future__ import annotations

import typer

from zoho_books_cli import config
from zoho_books_cli.client import ZohoBooksClient
from zoho_books_cli.commands import _shared

app = typer.Typer(
    help="Bank transaction operations (CRUD + match/categorize + statements).",
    no_args_is_help=True,
)
categorize_app = typer.Typer(
    help="Categorize an uncategorized bank transaction (one subcommand per target type).",
    no_args_is_help=True,
)
statements_app = typer.Typer(
    help="Bulk bank statement import operations.", no_args_is_help=True
)
app.add_typer(categorize_app, name="categorize")
app.add_typer(statements_app, name="statements")

BASE = "/banktransactions"
UNCAT = f"{BASE}/uncategorized"


@app.command("list")
def list_transactions(
    query: list[str] = typer.Option(
        None, "--query", "-q", help="Query params as key=value. May be repeated."
    ),
    page: int = typer.Option(None, "--page", help="Page number (1-indexed)."),
    per_page: int = typer.Option(None, "--per-page", help="Rows per page."),
):
    """List bank transactions. Returns one page plus page_context."""
    q = _shared.parse_query_pairs(query)
    if page is not None:
        q["page"] = str(page)
    if per_page is not None:
        q["per_page"] = str(per_page)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(BASE, query=q)
    _shared.emit_list(resp, "banktransactions")


@app.command("create")
def create_transaction(
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Create a bank transaction."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(BASE, json_body=json_body)
    _shared.emit_object(resp)


@app.command("get")
def get_transaction(
    transaction_id: str = typer.Argument(..., help="Zoho Books bank_transaction_id."),
):
    """Get a single bank transaction by ID."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"{BASE}/{transaction_id}")
    _shared.emit_object(resp)


@app.command("update")
def update_transaction(
    transaction_id: str = typer.Argument(..., help="Zoho Books bank_transaction_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Update a bank transaction by ID."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.put(f"{BASE}/{transaction_id}", json_body=json_body)
    _shared.emit_object(resp)


@app.command("delete")
def delete_transaction(
    transaction_id: str = typer.Argument(..., help="Zoho Books bank_transaction_id."),
):
    """Delete a bank transaction by ID."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"{BASE}/{transaction_id}")
    _shared.emit_action("transaction_id", transaction_id, resp)


@app.command("match")
def match_transaction(
    transaction_id: str = typer.Argument(..., help="Zoho Books bank_transaction_id."),
    body: str = typer.Option(
        ..., "--body", "-b", help="JSON body with transactions_to_be_matched. IDs must be strings."
    ),
):
    """Match an uncategorized transaction (POST /banktransactions/uncategorized/{id}/match)."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{UNCAT}/{transaction_id}/match", json_body=json_body)
    _shared.emit_action("transaction_id", transaction_id, resp)


@app.command("matches")
def list_matches(
    transaction_id: str = typer.Argument(..., help="Zoho Books bank_transaction_id."),
    query: list[str] = typer.Option(None, "--query", "-q", help="Query params as key=value."),
    page: int = typer.Option(None, "--page", help="Page number (1-indexed)."),
    per_page: int = typer.Option(None, "--per-page", help="Rows per page."),
):
    """List candidate matching transactions (GET /banktransactions/uncategorized/{id}/match)."""
    q = _shared.parse_query_pairs(query)
    if page is not None:
        q["page"] = str(page)
    if per_page is not None:
        q["per_page"] = str(per_page)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"{UNCAT}/{transaction_id}/match", query=q)
    _shared.emit_list(resp, "matching_transactions")


@app.command("unmatch")
def unmatch_transaction(
    transaction_id: str = typer.Argument(..., help="Zoho Books bank_transaction_id."),
):
    """Unmatch a matched transaction (POST /banktransactions/{id}/unmatch)."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{transaction_id}/unmatch")
    _shared.emit_action("transaction_id", transaction_id, resp)


@app.command("exclude")
def exclude_transaction(
    transaction_id: str = typer.Argument(..., help="Zoho Books bank_transaction_id."),
):
    """Exclude a transaction (POST /banktransactions/uncategorized/{id}/exclude)."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{UNCAT}/{transaction_id}/exclude")
    _shared.emit_action("transaction_id", transaction_id, resp)


@app.command("restore")
def restore_transaction(
    transaction_id: str = typer.Argument(..., help="Zoho Books bank_transaction_id."),
):
    """Restore an excluded transaction (POST /banktransactions/uncategorized/{id}/restore)."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{UNCAT}/{transaction_id}/restore")
    _shared.emit_action("transaction_id", transaction_id, resp)


@app.command("uncategorize")
def uncategorize_transaction(
    transaction_id: str = typer.Argument(..., help="Zoho Books bank_transaction_id."),
):
    """Uncategorize a categorized transaction (POST /banktransactions/{id}/uncategorize)."""
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(f"{BASE}/{transaction_id}/uncategorize")
    _shared.emit_action("transaction_id", transaction_id, resp)


# --- categorize sub-app ------------------------------------------------------


def _categorize(transaction_id: str, subpath: str, body: str | None) -> None:
    json_body = _shared.parse_body(body)
    path = f"{UNCAT}/{transaction_id}/categorize"
    if subpath:
        path = f"{path}/{subpath}"
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post(path, json_body=json_body)
    _shared.emit_action("transaction_id", transaction_id, resp)


@categorize_app.command("generic")
def categorize_generic(
    transaction_id: str = typer.Argument(..., help="Zoho Books bank_transaction_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Manual categorization (POST /banktransactions/uncategorized/{id}/categorize)."""
    _categorize(transaction_id, "", body)


@categorize_app.command("expense")
def categorize_expense(
    transaction_id: str = typer.Argument(..., help="Zoho Books bank_transaction_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Categorize as expense (POST .../categorize/expenses)."""
    _categorize(transaction_id, "expenses", body)


@categorize_app.command("vendor-payment")
def categorize_vendor_payment(
    transaction_id: str = typer.Argument(..., help="Zoho Books bank_transaction_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Categorize as vendor payment (POST .../categorize/vendorpayments)."""
    _categorize(transaction_id, "vendorpayments", body)


@categorize_app.command("customer-payment")
def categorize_customer_payment(
    transaction_id: str = typer.Argument(..., help="Zoho Books bank_transaction_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Categorize as customer payment (POST .../categorize/customerpayments)."""
    _categorize(transaction_id, "customerpayments", body)


@categorize_app.command("credit-note-refund")
def categorize_credit_note_refund(
    transaction_id: str = typer.Argument(..., help="Zoho Books bank_transaction_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Categorize as credit note refund (POST .../categorize/creditnoterefunds)."""
    _categorize(transaction_id, "creditnoterefunds", body)


@categorize_app.command("vendor-credit-refund")
def categorize_vendor_credit_refund(
    transaction_id: str = typer.Argument(..., help="Zoho Books bank_transaction_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Categorize as vendor credit refund (POST .../categorize/vendorcreditrefunds)."""
    _categorize(transaction_id, "vendorcreditrefunds", body)


@categorize_app.command("payment-refund")
def categorize_payment_refund(
    transaction_id: str = typer.Argument(..., help="Zoho Books bank_transaction_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Categorize as customer payment refund (POST .../categorize/paymentrefunds)."""
    _categorize(transaction_id, "paymentrefunds", body)


@categorize_app.command("vendor-payment-refund")
def categorize_vendor_payment_refund(
    transaction_id: str = typer.Argument(..., help="Zoho Books bank_transaction_id."),
    body: str = typer.Option(..., "--body", "-b", help="JSON body. IDs must be strings."),
):
    """Categorize as vendor payment refund (POST .../categorize/vendorpaymentrefunds)."""
    _categorize(transaction_id, "vendorpaymentrefunds", body)


# --- statements sub-app ------------------------------------------------------
# Statements are NOT under /banktransactions in Zoho's API — import is a
# top-level /bankstatements resource, and the get/delete operations live under
# /bankaccounts/{account_id}/statement/... We expose them under
# `bank-transactions statements` for user ergonomics since that's the natural
# conceptual grouping.


@statements_app.command("import")
def statements_import(
    body: str = typer.Option(
        ...,
        "--body",
        "-b",
        help="JSON body. Must include account_id, from_date, to_date, and file_content. "
        "IDs must be strings.",
    ),
):
    """Import a bank/credit-card statement (POST /bankstatements)."""
    json_body = _shared.parse_body(body)
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.post("/bankstatements", json_body=json_body)
    _shared.emit_object(resp)


@statements_app.command("last-imported")
def statements_last_imported(
    account_id: str = typer.Argument(..., help="Zoho Books bank account_id."),
):
    """Fetch the last imported statement for an account.

    (GET /bankaccounts/{account_id}/statement/lastimported)
    """
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.get(f"/bankaccounts/{account_id}/statement/lastimported")
    _shared.emit_object(resp)


@statements_app.command("delete")
def statements_delete(
    account_id: str = typer.Argument(..., help="Zoho Books bank account_id."),
    statement_id: str = typer.Argument(..., help="Zoho Books statement_id to delete."),
):
    """Delete a specific imported statement.

    (DELETE /bankaccounts/{account_id}/statement/{statement_id})
    """
    cfg = config.load()
    with ZohoBooksClient(cfg) as client:
        resp = client.delete(f"/bankaccounts/{account_id}/statement/{statement_id}")
    _shared.emit_action("statement_id", statement_id, resp)
