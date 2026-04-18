"""Thin-wrapper tests for `zb contacts ...`."""

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
        mock.get(f"{BASE}/contacts").mock(
            return_value=httpx.Response(
                200,
                json={
                    "contacts": [{"contact_id": "C1"}],
                    "page_context": {"page": 1, "has_more_page": False},
                },
            )
        )
        result = runner.invoke(app, ["contacts", "list"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["items"] == [{"contact_id": "C1"}]


def test_search_uses_name_contains(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.get(
            f"{BASE}/contacts",
            params={"organization_id": "123456", "contact_name_contains": "Reverb"},
        ).mock(return_value=httpx.Response(200, json={"contacts": [], "page_context": {}}))
        result = runner.invoke(app, ["contacts", "search", "Reverb"])
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_get(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/contacts/C1").mock(
            return_value=httpx.Response(200, json={"contact": {"contact_id": "C1"}})
        )
        result = runner.invoke(app, ["contacts", "get", "C1"])
    assert result.exit_code == 0, result.stderr


def test_create_preserves_large_ids(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    big = 9820000005670010000
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/contacts").mock(
            return_value=httpx.Response(201, json={"contact": {}})
        )
        result = runner.invoke(
            app,
            [
                "contacts",
                "create",
                "--body",
                f'{{"contact_name": "X", "currency_id": {big}}}',
            ],
        )
    assert result.exit_code == 0, result.stderr
    outgoing = json.loads(route.calls[0].request.content)
    assert outgoing["currency_id"] == big


def test_update(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.put(f"{BASE}/contacts/C1").mock(
            return_value=httpx.Response(200, json={"contact": {}})
        )
        result = runner.invoke(app, ["contacts", "update", "C1", "--body", '{"notes": "updated"}'])
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_update_by_custom_field_sets_headers(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.put(f"{BASE}/contacts").mock(
            return_value=httpx.Response(200, json={"contact": {}})
        )
        result = runner.invoke(
            app,
            [
                "contacts",
                "update-by-custom-field",
                "--key",
                "cf_external_id",
                "--value",
                "abc",
                "--body",
                '{"notes": "updated"}',
            ],
        )
    assert result.exit_code == 0, result.stderr
    req = route.calls[0].request
    assert req.headers["X-Unique-Identifier-Key"] == "cf_external_id"


def test_delete(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.delete(f"{BASE}/contacts/C1").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "deleted"})
        )
        result = runner.invoke(app, ["contacts", "delete", "C1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["contact_id"] == "C1"


def test_mark_active(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/contacts/C1/active").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "activated"})
        )
        result = runner.invoke(app, ["contacts", "mark-active", "C1"])
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_mark_inactive(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/contacts/C1/inactive").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "deactivated"})
        )
        result = runner.invoke(app, ["contacts", "mark-inactive", "C1"])
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_comments(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/contacts/C1/comments").mock(
            return_value=httpx.Response(
                200, json={"comments": [{"comment_id": "K1"}], "page_context": {}}
            )
        )
        result = runner.invoke(app, ["contacts", "comments", "C1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["items"] == [{"comment_id": "K1"}]
