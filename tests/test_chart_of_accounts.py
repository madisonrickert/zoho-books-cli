"""Thin-wrapper tests for `zb chart-of-accounts ...`."""

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
        mock.get(f"{BASE}/chartofaccounts").mock(
            return_value=httpx.Response(
                200,
                json={
                    "chartofaccounts": [{"account_id": "A1"}],
                    "page_context": {"page": 1, "has_more_page": False},
                },
            )
        )
        result = runner.invoke(app, ["chart-of-accounts", "list"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["items"] == [{"account_id": "A1"}]


def test_list_forwards_filter_query(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.get(
            f"{BASE}/chartofaccounts",
            params={
                "organization_id": "123456",
                "filter_by": "AccountType.PaidThrough",
                "per_page": "200",
            },
        ).mock(return_value=httpx.Response(200, json={"chartofaccounts": [], "page_context": {}}))
        result = runner.invoke(
            app,
            [
                "chart-of-accounts",
                "list",
                "--query",
                "filter_by=AccountType.PaidThrough",
                "--per-page",
                "200",
            ],
        )
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_get(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/chartofaccounts/A1").mock(
            return_value=httpx.Response(200, json={"chart_of_account": {"account_id": "A1"}})
        )
        result = runner.invoke(app, ["chart-of-accounts", "get", "A1"])
    assert result.exit_code == 0, result.stderr


def test_create(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/chartofaccounts").mock(
            return_value=httpx.Response(201, json={"chart_of_account": {}})
        )
        result = runner.invoke(
            app,
            [
                "chart-of-accounts",
                "create",
                "--body",
                '{"account_name": "Test", "account_type": "expense"}',
            ],
        )
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_update(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.put(f"{BASE}/chartofaccounts/A1").mock(
            return_value=httpx.Response(200, json={"chart_of_account": {}})
        )
        result = runner.invoke(
            app,
            ["chart-of-accounts", "update", "A1", "--body", '{"account_name": "Renamed"}'],
        )
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_delete(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.delete(f"{BASE}/chartofaccounts/A1").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "deleted"})
        )
        result = runner.invoke(app, ["chart-of-accounts", "delete", "A1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["account_id"] == "A1"


def test_mark_active(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/chartofaccounts/A1/active").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "activated"})
        )
        result = runner.invoke(app, ["chart-of-accounts", "mark-active", "A1"])
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_mark_inactive(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/chartofaccounts/A1/inactive").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "deactivated"})
        )
        result = runner.invoke(app, ["chart-of-accounts", "mark-inactive", "A1"])
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_transactions_list(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/chartofaccounts/transactions").mock(
            return_value=httpx.Response(
                200, json={"transactions": [{"transaction_id": "T1"}], "page_context": {}}
            )
        )
        result = runner.invoke(app, ["chart-of-accounts", "transactions", "list"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["items"] == [{"transaction_id": "T1"}]


def test_transactions_delete(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.delete(f"{BASE}/chartofaccounts/transactions/T1").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "deleted"})
        )
        result = runner.invoke(app, ["chart-of-accounts", "transactions", "delete", "T1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["transaction_id"] == "T1"
