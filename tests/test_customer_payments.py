"""Thin-wrapper tests for `zb customer-payments ...`."""

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
        mock.get(f"{BASE}/customerpayments").mock(
            return_value=httpx.Response(
                200,
                json={
                    "customerpayments": [{"payment_id": "P1"}],
                    "page_context": {"page": 1, "has_more_page": False},
                },
            )
        )
        result = runner.invoke(app, ["customer-payments", "list"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["items"] == [{"payment_id": "P1"}]


def test_list_forwards_query_and_pagination(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.get(
            f"{BASE}/customerpayments",
            params={
                "organization_id": "123456",
                "customer_id": "9820000005670010000",
                "page": "2",
                "per_page": "50",
            },
        ).mock(return_value=httpx.Response(200, json={"customerpayments": [], "page_context": {}}))
        result = runner.invoke(
            app,
            [
                "customer-payments",
                "list",
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


def test_get(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/customerpayments/P1").mock(
            return_value=httpx.Response(200, json={"payment": {"payment_id": "P1"}})
        )
        result = runner.invoke(app, ["customer-payments", "get", "P1"])
    assert result.exit_code == 0, result.stderr


def test_create_posts_body_preserving_large_ids(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    big = 9820000005670010000
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/customerpayments").mock(
            return_value=httpx.Response(201, json={"payment": {}})
        )
        result = runner.invoke(
            app,
            ["customer-payments", "create", "--body", f'{{"customer_id": {big}, "amount": 100}}'],
        )
    assert result.exit_code == 0, result.stderr
    outgoing = json.loads(route.calls[0].request.content)
    assert outgoing["customer_id"] == big


def test_update(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.put(f"{BASE}/customerpayments/P1").mock(
            return_value=httpx.Response(200, json={"payment": {}})
        )
        result = runner.invoke(
            app,
            [
                "customer-payments",
                "update",
                "P1",
                "--body",
                '{"project_id": "9820000005670010000"}',
            ],
        )
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_update_by_custom_field_sets_headers(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.put(f"{BASE}/customerpayments").mock(
            return_value=httpx.Response(200, json={"payment": {}})
        )
        result = runner.invoke(
            app,
            [
                "customer-payments",
                "update-by-custom-field",
                "--key",
                "cf_external_id",
                "--value",
                "abc123",
                "--body",
                '{"reference_number": "ref-new"}',
                "--upsert",
            ],
        )
    assert result.exit_code == 0, result.stderr
    req = route.calls[0].request
    assert req.headers["X-Unique-Identifier-Key"] == "cf_external_id"
    assert req.headers["X-Unique-Identifier-Value"] == "abc123"
    assert req.headers["X-Upsert"] == "true"


def test_delete(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.delete(f"{BASE}/customerpayments/P1").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "deleted"})
        )
        result = runner.invoke(app, ["customer-payments", "delete", "P1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["payment_id"] == "P1"


def test_refunds_list(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/customerpayments/P1/refunds").mock(
            return_value=httpx.Response(
                200,
                json={"payment_refunds": [{"refund_id": "R1"}], "page_context": {}},
            )
        )
        result = runner.invoke(app, ["customer-payments", "refunds", "list", "P1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["items"] == [{"refund_id": "R1"}]


def test_refunds_create(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/customerpayments/P1/refunds").mock(
            return_value=httpx.Response(201, json={"payment_refund": {"refund_id": "R1"}})
        )
        result = runner.invoke(
            app,
            ["customer-payments", "refunds", "create", "P1", "--body", '{"amount": 25.00}'],
        )
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_refunds_get(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/customerpayments/P1/refunds/R1").mock(
            return_value=httpx.Response(200, json={"payment_refund": {"refund_id": "R1"}})
        )
        result = runner.invoke(app, ["customer-payments", "refunds", "get", "P1", "R1"])
    assert result.exit_code == 0, result.stderr


def test_refunds_delete(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.delete(f"{BASE}/customerpayments/P1/refunds/R1").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "deleted"})
        )
        result = runner.invoke(app, ["customer-payments", "refunds", "delete", "P1", "R1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["refund_id"] == "R1"
