"""Thin-wrapper tests for `zb bank-rules ...`."""

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
        mock.get(f"{BASE}/bankaccounts/rules").mock(
            return_value=httpx.Response(
                200,
                json={
                    "rules": [{"rule_id": "R1"}],
                    "page_context": {"page": 1, "has_more_page": False},
                },
            )
        )
        result = runner.invoke(app, ["bank-rules", "list", "--query", "account_id=982000000567010"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["items"] == [{"rule_id": "R1"}]


def test_get(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/bankaccounts/rules/R1").mock(
            return_value=httpx.Response(200, json={"rule": {"rule_id": "R1"}})
        )
        result = runner.invoke(app, ["bank-rules", "get", "R1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["rule"]["rule_id"] == "R1"


def test_create_preserves_large_ids(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    big = 9820000005670010000
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/bankaccounts/rules").mock(
            return_value=httpx.Response(201, json={"rule": {}})
        )
        result = runner.invoke(
            app,
            [
                "bank-rules",
                "create",
                "--body",
                f'{{"rule_name": "Stripe inflows", "account_id": {big}, "target_type": "deposit"}}',
            ],
        )
    assert result.exit_code == 0, result.stderr
    outgoing = json.loads(route.calls[0].request.content)
    assert outgoing["account_id"] == big


def test_update(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.put(f"{BASE}/bankaccounts/rules/R1").mock(
            return_value=httpx.Response(200, json={"rule": {}})
        )
        result = runner.invoke(
            app, ["bank-rules", "update", "R1", "--body", '{"rule_name": "renamed"}']
        )
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_delete(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.delete(f"{BASE}/bankaccounts/rules/R1").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "deleted"})
        )
        result = runner.invoke(app, ["bank-rules", "delete", "R1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["rule_id"] == "R1"
    assert payload["data"]["acted"] is True
