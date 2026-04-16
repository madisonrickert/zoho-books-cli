"""Thin-wrapper tests for `zb bank-transactions ...`.

Verifies the asymmetric path layout: match/matches/exclude/restore sit under
/banktransactions/uncategorized/{id}/..., but unmatch/uncategorize sit under
/banktransactions/{id}/... Categorize is a family of 8 endpoints.
"""

from __future__ import annotations

import json
import time

import httpx
import respx
from typer.testing import CliRunner

from zoho_books_cli.cli import app

BASE = "https://www.zohoapis.com/books/v3"


def _setup_auth(storage_state):
    storage_state.update(
        {
            "client_id": "cid",
            "client_secret": "csec",
            "refresh_token": "rtok",
            "access_token": "atok",
            "expires_at": time.time() + 3600,
            "region": "us",
            "org_id": "123456",
        }
    )


def test_list(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/banktransactions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "banktransactions": [{"transaction_id": "T1"}],
                    "page_context": {"page": 1, "has_more_page": False},
                },
            )
        )
        result = runner.invoke(app, ["bank-transactions", "list"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["items"] == [{"transaction_id": "T1"}]


def test_list_forwards_query_and_pagination(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.get(
            f"{BASE}/banktransactions",
            params={
                "organization_id": "123456",
                "account_id": "9820000005670010000",
                "page": "3",
                "per_page": "25",
            },
        ).mock(return_value=httpx.Response(200, json={"banktransactions": [], "page_context": {}}))
        result = runner.invoke(
            app,
            [
                "bank-transactions",
                "list",
                "--query",
                "account_id=9820000005670010000",
                "--page",
                "3",
                "--per-page",
                "25",
            ],
        )
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_get(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/banktransactions/T1").mock(
            return_value=httpx.Response(200, json={"banktransaction": {"transaction_id": "T1"}})
        )
        result = runner.invoke(app, ["bank-transactions", "get", "T1"])
    assert result.exit_code == 0, result.stderr


def test_create_posts_body_preserving_large_ids(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    big = 9820000005670010000
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/banktransactions").mock(
            return_value=httpx.Response(201, json={"banktransaction": {}})
        )
        result = runner.invoke(
            app,
            ["bank-transactions", "create", "--body", f'{{"account_id": {big}, "amount": 10.50}}'],
        )
    assert result.exit_code == 0, result.stderr
    outgoing = json.loads(route.calls[0].request.content)
    assert outgoing["account_id"] == big


def test_update_puts_body(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.put(f"{BASE}/banktransactions/T1").mock(
            return_value=httpx.Response(200, json={"banktransaction": {}})
        )
        result = runner.invoke(
            app, ["bank-transactions", "update", "T1", "--body", '{"description": "updated"}']
        )
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_delete(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.delete(f"{BASE}/banktransactions/T1").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "deleted"})
        )
        result = runner.invoke(app, ["bank-transactions", "delete", "T1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["transaction_id"] == "T1"


def test_match_uses_uncategorized_subpath(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/banktransactions/uncategorized/T1/match").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "matched"})
        )
        result = runner.invoke(
            app,
            [
                "bank-transactions",
                "match",
                "T1",
                "--body",
                '{"transactions_to_be_matched": [{"transaction_id": "9820000005670010001"}]}',
            ],
        )
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_matches_is_get_on_uncategorized_match(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/banktransactions/uncategorized/T1/match").mock(
            return_value=httpx.Response(
                200,
                json={
                    "matching_transactions": [{"transaction_id": "M1"}],
                    "page_context": {},
                },
            )
        )
        result = runner.invoke(app, ["bank-transactions", "matches", "T1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["items"] == [{"transaction_id": "M1"}]


def test_unmatch_on_base_path_not_uncategorized(in_memory_storage):
    """Regression guard for path asymmetry — unmatch does NOT go through /uncategorized."""
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/banktransactions/T1/unmatch").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "unmatched"})
        )
        result = runner.invoke(app, ["bank-transactions", "unmatch", "T1"])
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_exclude_on_uncategorized_path(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/banktransactions/uncategorized/T1/exclude").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "excluded"})
        )
        result = runner.invoke(app, ["bank-transactions", "exclude", "T1"])
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_restore_on_uncategorized_path(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/banktransactions/uncategorized/T1/restore").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "restored"})
        )
        result = runner.invoke(app, ["bank-transactions", "restore", "T1"])
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_uncategorize_on_base_path_not_uncategorized(in_memory_storage):
    """Regression guard for path asymmetry — uncategorize lives on the base path."""
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/banktransactions/T1/uncategorize").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "uncategorized"})
        )
        result = runner.invoke(app, ["bank-transactions", "uncategorize", "T1"])
    assert result.exit_code == 0, result.stderr
    assert route.called


# --- categorize family -------------------------------------------------------

CATEGORIZE_CASES = [
    ("generic", ""),
    ("expense", "expenses"),
    ("vendor-payment", "vendorpayments"),
    ("customer-payment", "customerpayments"),
    ("credit-note-refund", "creditnoterefunds"),
    ("vendor-credit-refund", "vendorcreditrefunds"),
    ("payment-refund", "paymentrefunds"),
    ("vendor-payment-refund", "vendorpaymentrefunds"),
]


def test_categorize_variants_hit_correct_subpaths(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    for verb, subpath in CATEGORIZE_CASES:
        expected = f"{BASE}/banktransactions/uncategorized/T1/categorize"
        if subpath:
            expected = f"{expected}/{subpath}"
        with respx.mock() as mock:
            route = mock.post(expected).mock(
                return_value=httpx.Response(200, json={"code": 0, "message": "categorized"})
            )
            result = runner.invoke(
                app,
                ["bank-transactions", "categorize", verb, "T1", "--body", '{"account_id": "A1"}'],
            )
        assert result.exit_code == 0, f"{verb}: {result.stderr}"
        assert route.called, f"{verb} did not hit {expected}"


# --- statements sub-app ------------------------------------------------------


def test_statements_import_posts_to_bankstatements_top_level(in_memory_storage):
    """Regression guard: statement import is POST /bankstatements, not under /banktransactions."""
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/bankstatements").mock(
            return_value=httpx.Response(201, json={"statement": {"statement_id": "S1"}})
        )
        result = runner.invoke(
            app,
            [
                "bank-transactions",
                "statements",
                "import",
                "--body",
                '{"account_id": "A1", "from_date": "2026-01-01"}',
            ],
        )
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_statements_last_imported_requires_account_id_and_hits_correct_path(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.get(f"{BASE}/bankaccounts/A1/statement/lastimported").mock(
            return_value=httpx.Response(200, json={"statement": {"statement_id": "S1"}})
        )
        result = runner.invoke(app, ["bank-transactions", "statements", "last-imported", "A1"])
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_statements_delete_by_account_and_statement_id(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.delete(f"{BASE}/bankaccounts/A1/statement/S1").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "deleted"})
        )
        result = runner.invoke(app, ["bank-transactions", "statements", "delete", "A1", "S1"])
    assert result.exit_code == 0, result.stderr
    assert route.called
    payload = json.loads(result.stdout)
    assert payload["data"]["statement_id"] == "S1"
    assert payload["data"]["acted"] is True
