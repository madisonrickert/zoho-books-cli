"""Thin-wrapper tests for `zb recurring-invoices ...`."""

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
        mock.get(f"{BASE}/recurringinvoices").mock(
            return_value=httpx.Response(
                200,
                json={
                    "recurring_invoices": [{"recurring_invoice_id": "R1"}],
                    "page_context": {"page": 1, "has_more_page": False},
                },
            )
        )
        result = runner.invoke(app, ["recurring-invoices", "list"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["items"] == [{"recurring_invoice_id": "R1"}]


def test_get(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/recurringinvoices/R1").mock(
            return_value=httpx.Response(
                200, json={"recurring_invoice": {"recurring_invoice_id": "R1"}}
            )
        )
        result = runner.invoke(app, ["recurring-invoices", "get", "R1"])
    assert result.exit_code == 0, result.stderr


def test_create_preserves_large_ids(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    big = 9820000005670010000
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/recurringinvoices").mock(
            return_value=httpx.Response(201, json={"recurring_invoice": {}})
        )
        result = runner.invoke(
            app,
            [
                "recurring-invoices",
                "create",
                "--body",
                f'{{"customer_id": {big}, "recurrence_frequency": "months"}}',
            ],
        )
    assert result.exit_code == 0, result.stderr
    outgoing = json.loads(route.calls[0].request.content)
    assert outgoing["customer_id"] == big


def test_update(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.put(f"{BASE}/recurringinvoices/R1").mock(
            return_value=httpx.Response(200, json={"recurring_invoice": {}})
        )
        result = runner.invoke(
            app, ["recurring-invoices", "update", "R1", "--body", '{"notes": "n"}']
        )
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_update_by_custom_field(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.put(f"{BASE}/recurringinvoices").mock(
            return_value=httpx.Response(200, json={"recurring_invoice": {}})
        )
        result = runner.invoke(
            app,
            [
                "recurring-invoices",
                "update-by-custom-field",
                "--key",
                "cf_external_id",
                "--value",
                "abc",
                "--upsert",
                "--body",
                '{"customer_id": "C1"}',
            ],
        )
    assert result.exit_code == 0, result.stderr
    h = route.calls[0].request.headers
    assert h["X-Unique-Identifier-Key"] == "cf_external_id"
    assert h["X-Upsert"] == "true"


def test_delete(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.delete(f"{BASE}/recurringinvoices/R1").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "deleted"})
        )
        result = runner.invoke(app, ["recurring-invoices", "delete", "R1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["recurring_invoice_id"] == "R1"


def test_stop(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/recurringinvoices/R1/status/stop").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "stopped"})
        )
        result = runner.invoke(app, ["recurring-invoices", "stop", "R1"])
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_resume(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/recurringinvoices/R1/status/resume").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "resumed"})
        )
        result = runner.invoke(app, ["recurring-invoices", "resume", "R1"])
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_history(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/recurringinvoices/R1/comments").mock(
            return_value=httpx.Response(200, json={"comments": [{"comment_id": "C1"}]})
        )
        result = runner.invoke(app, ["recurring-invoices", "history", "R1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["items"] == [{"comment_id": "C1"}]


def test_templates_apply(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.put(f"{BASE}/recurringinvoices/R1/templates/T1").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "applied"})
        )
        result = runner.invoke(app, ["recurring-invoices", "templates", "apply", "R1", "T1"])
    assert result.exit_code == 0, result.stderr
    assert route.called
