"""Tests for the --dry-run global flag.

Dry-run short-circuits before httpx.request and emits the would-be request
(method, url, query, headers, body, files) as the success payload. No HTTP
call is made; no token refresh is triggered.
"""

from __future__ import annotations

import json
import time

import httpx
import respx
from typer.testing import CliRunner

from zoho_books_cli import output
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


def _reset_dry_run():
    """Dry-run is module-level state; tests must reset it after each invoke."""
    output.set_dry_run(False)


def test_dry_run_get_does_not_call_api(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    try:
        with respx.mock(assert_all_called=False) as mock:
            route = mock.get(f"{BASE}/contacts").mock(
                return_value=httpx.Response(200, json={"contacts": [], "page_context": {}})
            )
            result = runner.invoke(app, ["--dry-run", "contacts", "list"])
        assert result.exit_code == 0, result.stderr
        assert not route.called, "dry-run must not hit the network"
        payload = json.loads(result.stdout)
        assert payload["ok"] is True
        assert payload["data"]["dry_run"] is True
        assert payload["data"]["method"] == "GET"
        assert payload["data"]["url"].endswith("/books/v3/contacts")
        assert payload["data"]["query"]["organization_id"] == "123456"
    finally:
        _reset_dry_run()


def test_dry_run_post_includes_body(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    try:
        with respx.mock(assert_all_called=False) as mock:
            route = mock.post(f"{BASE}/expenses").mock(
                return_value=httpx.Response(201, json={"expense": {}})
            )
            result = runner.invoke(
                app,
                [
                    "--dry-run",
                    "expenses",
                    "create",
                    "--body",
                    '{"account_id": "9820000005670010000", "amount": 42.50}',
                ],
            )
        assert result.exit_code == 0, result.stderr
        assert not route.called
        payload = json.loads(result.stdout)
        assert payload["data"]["method"] == "POST"
        assert payload["data"]["json_body"]["account_id"] == "9820000005670010000"
        assert payload["data"]["json_body"]["amount"] == 42.5
    finally:
        _reset_dry_run()


def test_dry_run_put_preserves_caller_headers(in_memory_storage):
    """update-by-custom-field uses X-Unique-Identifier-* headers; dry-run must show them."""
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    try:
        with respx.mock(assert_all_called=False) as mock:
            mock.put(f"{BASE}/contacts").mock(return_value=httpx.Response(200, json={}))
            result = runner.invoke(
                app,
                [
                    "--dry-run",
                    "contacts",
                    "update-by-custom-field",
                    "--key",
                    "cf_external_id",
                    "--value",
                    "abc",
                    "--body",
                    '{"notes": "x"}',
                ],
            )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        headers = payload["data"]["headers"]
        assert headers["X-Unique-Identifier-Key"] == "cf_external_id"
        assert headers["X-Unique-Identifier-Value"] == "abc"
        # Authorization header must NOT leak into dry-run output.
        assert "Authorization" not in headers
        assert not any(k.lower() == "authorization" for k in headers)
    finally:
        _reset_dry_run()


def test_dry_run_delete(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    try:
        with respx.mock(assert_all_called=False) as mock:
            route = mock.delete(f"{BASE}/expenses/EXP1").mock(
                return_value=httpx.Response(200, json={})
            )
            result = runner.invoke(app, ["--dry-run", "expenses", "delete", "EXP1"])
        assert result.exit_code == 0, result.stderr
        assert not route.called
        payload = json.loads(result.stdout)
        assert payload["data"]["method"] == "DELETE"
        assert payload["data"]["url"].endswith("/books/v3/expenses/EXP1")
    finally:
        _reset_dry_run()


def test_dry_run_upload_describes_files_without_sending(in_memory_storage, sample_receipt):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    try:
        with respx.mock(assert_all_called=False) as mock:
            route = mock.post(f"{BASE}/expenses/EXP1/receipt").mock(
                return_value=httpx.Response(200, json={})
            )
            result = runner.invoke(
                app,
                [
                    "--dry-run",
                    "expenses",
                    "receipt",
                    "upload",
                    "EXP1",
                    str(sample_receipt),
                ],
            )
        assert result.exit_code == 0, result.stderr
        assert not route.called
        payload = json.loads(result.stdout)
        files = payload["data"]["files"]
        assert files is not None
        assert "receipt" in files
        assert files["receipt"]["filename"] == sample_receipt.name
    finally:
        _reset_dry_run()
