"""Tests for `zb org get|update` API commands."""

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


def test_org_get(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/organizations/123456").mock(
            return_value=httpx.Response(
                200,
                json={
                    "organization": {
                        "organization_id": "123456",
                        "name": "Acme",
                        "currency_code": "USD",
                    }
                },
            )
        )
        result = runner.invoke(app, ["org", "get", "123456"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["organization"]["organization_id"] == "123456"


def test_org_update(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.put(f"{BASE}/organizations/123456").mock(
            return_value=httpx.Response(200, json={"organization": {"name": "Renamed"}})
        )
        result = runner.invoke(app, ["org", "update", "123456", "--body", '{"name": "Renamed"}'])
    assert result.exit_code == 0, result.stderr
    assert json.loads(route.calls[0].request.content) == {"name": "Renamed"}


def test_org_update_preserves_large_ids(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    big = 9820000005670010000
    with respx.mock() as mock:
        route = mock.put(f"{BASE}/organizations/123456").mock(
            return_value=httpx.Response(200, json={"organization": {}})
        )
        result = runner.invoke(
            app,
            [
                "org",
                "update",
                "123456",
                "--body",
                f'{{"currency_id": {big}}}',
            ],
        )
    assert result.exit_code == 0, result.stderr
    outgoing = json.loads(route.calls[0].request.content)
    assert outgoing["currency_id"] == big
