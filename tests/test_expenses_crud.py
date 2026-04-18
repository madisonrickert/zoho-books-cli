"""Thin-wrapper CRUD + comments tests for `zb expenses ...`."""

from __future__ import annotations

import json
import time

import httpx
import respx
from typer.testing import CliRunner

from zoho_books_cli.cli import app


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


BASE = "https://www.zohoapis.com/books/v3"


def test_list_exposes_items_and_page_context(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/expenses").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "message": "success",
                    "expenses": [{"expense_id": "E1"}],
                    "page_context": {"page": 1, "has_more_page": False},
                },
            )
        )
        result = runner.invoke(app, ["expenses", "list", "--per-page", "5"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["items"] == [{"expense_id": "E1"}]
    assert payload["data"]["page_context"] == {"page": 1, "has_more_page": False}


def test_list_forwards_query_pairs_and_pagination(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.get(
            f"{BASE}/expenses",
            params={
                "organization_id": "123456",
                "status": "unfiled",
                "customer_id": "9820000005670010000",
                "page": "2",
                "per_page": "50",
            },
        ).mock(return_value=httpx.Response(200, json={"expenses": [], "page_context": {}}))
        result = runner.invoke(
            app,
            [
                "expenses",
                "list",
                "--query",
                "status=unfiled",
                "--query",
                "customer_id=9820000005670010000",
                "--page",
                "2",
                "--per-page",
                "50",
            ],
        )
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_get_expense_hits_correct_path(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/expenses/EXP1").mock(
            return_value=httpx.Response(
                200, json={"code": 0, "message": "success", "expense": {"expense_id": "EXP1"}}
            )
        )
        result = runner.invoke(app, ["expenses", "get", "EXP1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"] == {"expense": {"expense_id": "EXP1"}}


def test_create_posts_body(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    body = {"account_id": "9820000005670010000", "amount": 42.50, "date": "2026-04-15"}
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/expenses").mock(
            return_value=httpx.Response(201, json={"expense": {"expense_id": "NEW"}})
        )
        result = runner.invoke(app, ["expenses", "create", "--body", json.dumps(body)])
    assert result.exit_code == 0, result.stderr
    req = route.calls[0].request
    assert json.loads(req.content) == body


def test_create_preserves_large_integer_ids_in_outgoing_body(in_memory_storage):
    """Invariant: 19-digit IDs passed as JSON numbers must survive round-trip."""
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    big = 9820000005670010000
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/expenses").mock(
            return_value=httpx.Response(201, json={"expense": {}})
        )
        result = runner.invoke(app, ["expenses", "create", "--body", f'{{"customer_id": {big}}}'])
    assert result.exit_code == 0, result.stderr
    outgoing = json.loads(route.calls[0].request.content)
    assert outgoing["customer_id"] == big


def test_update_puts_body(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.put(f"{BASE}/expenses/EXP1").mock(
            return_value=httpx.Response(200, json={"expense": {"expense_id": "EXP1"}})
        )
        result = runner.invoke(app, ["expenses", "update", "EXP1", "--body", '{"amount": 99.99}'])
    assert result.exit_code == 0, result.stderr
    assert json.loads(route.calls[0].request.content) == {"amount": 99.99}


def test_update_by_custom_field_sends_identifier_as_headers(in_memory_storage):
    """Regression guard: identifier goes in X-Unique-Identifier-* headers, not body."""
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.put(f"{BASE}/expenses").mock(
            return_value=httpx.Response(200, json={"expense": {"expense_id": "EXP9"}})
        )
        result = runner.invoke(
            app,
            [
                "expenses",
                "update-by-custom-field",
                "--key",
                "cf_external_id",
                "--value",
                "ABC-123",
                "--body",
                '{"amount": 12.34}',
            ],
        )
    assert result.exit_code == 0, result.stderr
    req = route.calls[0].request
    assert req.headers["X-Unique-Identifier-Key"] == "cf_external_id"
    assert req.headers["X-Unique-Identifier-Value"] == "ABC-123"
    assert "X-Upsert" not in req.headers
    assert json.loads(req.content) == {"amount": 12.34}


def test_update_by_custom_field_upsert_flag_sets_header(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.put(f"{BASE}/expenses").mock(
            return_value=httpx.Response(200, json={"expense": {"expense_id": "EXP9"}})
        )
        result = runner.invoke(
            app,
            [
                "expenses",
                "update-by-custom-field",
                "--key",
                "cf_external_id",
                "--value",
                "ABC-123",
                "--body",
                '{"amount": 12.34}',
                "--upsert",
            ],
        )
    assert result.exit_code == 0, result.stderr
    assert route.calls[0].request.headers["X-Upsert"] == "true"


def test_delete_hits_correct_path(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.delete(f"{BASE}/expenses/EXP1").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "deleted"})
        )
        result = runner.invoke(app, ["expenses", "delete", "EXP1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["expense_id"] == "EXP1"
    assert payload["data"]["acted"] is True


def test_comments_list(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/expenses/EXP1/comments").mock(
            return_value=httpx.Response(
                200,
                json={
                    "comments": [{"comment_id": "C1", "description": "note"}],
                    "page_context": {"page": 1, "has_more_page": False},
                },
            )
        )
        result = runner.invoke(app, ["expenses", "comments", "list", "EXP1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["items"] == [{"comment_id": "C1", "description": "note"}]


def test_receipt_get_downloads_binary_to_file(in_memory_storage, tmp_path):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    pdf_bytes = b"%PDF-1.4\nfake pdf body\n"
    out = tmp_path / "out.pdf"
    with respx.mock() as mock:
        mock.get(f"{BASE}/expenses/EXP1/receipt").mock(
            return_value=httpx.Response(
                200, content=pdf_bytes, headers={"content-type": "application/pdf"}
            )
        )
        result = runner.invoke(app, ["expenses", "receipt", "get", "EXP1", "--output", str(out)])
    assert result.exit_code == 0, result.stderr
    assert out.read_bytes() == pdf_bytes
    payload = json.loads(result.stdout)
    assert payload["data"]["expense_id"] == "EXP1"
    assert payload["data"]["saved_to"] == str(out)
    assert payload["data"]["size_bytes"] == len(pdf_bytes)
    assert payload["data"]["content_type"] == "application/pdf"


def test_response_passes_through_large_ids_verbatim(in_memory_storage):
    """Zoho-side IDs in the response must flow through unchanged."""
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    big_id_str = "9820000005670010001"
    with respx.mock() as mock:
        mock.get(f"{BASE}/expenses/{big_id_str}").mock(
            return_value=httpx.Response(
                200, json={"expense": {"expense_id": big_id_str, "customer_id": big_id_str}}
            )
        )
        result = runner.invoke(app, ["expenses", "get", big_id_str])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["expense"]["expense_id"] == big_id_str
    assert payload["data"]["expense"]["customer_id"] == big_id_str
