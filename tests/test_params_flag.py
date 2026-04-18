"""Tests for the --params '{JSON}' alternative to --query k=v."""

from __future__ import annotations

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


def test_params_json_object(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.get(
            f"{BASE}/contacts",
            params={
                "organization_id": "123456",
                "contact_name_contains": "Reverb",
                "per_page": "50",
            },
        ).mock(return_value=httpx.Response(200, json={"contacts": [], "page_context": {}}))
        result = runner.invoke(
            app,
            [
                "contacts",
                "list",
                "--params",
                '{"contact_name_contains": "Reverb", "per_page": 50}',
            ],
        )
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_params_merges_with_query_pairs(in_memory_storage):
    """--query k=v is applied first; --params keys override on conflict."""
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.get(
            f"{BASE}/banktransactions",
            params={
                "organization_id": "123456",
                "account_id": "A1",
                "filter_by": "Status.All",
                "per_page": "200",
            },
        ).mock(return_value=httpx.Response(200, json={"banktransactions": [], "page_context": {}}))
        result = runner.invoke(
            app,
            [
                "bank-transactions",
                "list",
                "--query",
                "account_id=A1",
                "--query",
                "filter_by=Status.Unreconciled",  # overridden below
                "--params",
                '{"filter_by": "Status.All", "per_page": 200}',
            ],
        )
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_params_booleans_stringify(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.get(
            f"{BASE}/expenses",
            params={"organization_id": "123456", "include_inactive": "true"},
        ).mock(return_value=httpx.Response(200, json={"expenses": [], "page_context": {}}))
        result = runner.invoke(
            app,
            ["expenses", "list", "--params", '{"include_inactive": true}'],
        )
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_params_null_removes_key(in_memory_storage):
    """Passing null in --params explicitly unsets a key that --query set."""
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.get(
            f"{BASE}/contacts",
            params={"organization_id": "123456"},
        ).mock(return_value=httpx.Response(200, json={"contacts": [], "page_context": {}}))
        result = runner.invoke(
            app,
            [
                "contacts",
                "list",
                "--query",
                "status=active",
                "--params",
                '{"status": null}',
            ],
        )
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_params_invalid_json_raises_validation_error(in_memory_storage):
    """--params that isn't valid JSON surfaces as a typed ValidationError."""
    from zoho_books_cli.errors import ValidationError

    _setup_auth(in_memory_storage)
    runner = CliRunner()
    result = runner.invoke(app, ["contacts", "list", "--params", "not-json"])
    assert result.exit_code != 0
    assert isinstance(result.exception, ValidationError)


def test_params_non_object_raises_validation_error(in_memory_storage):
    """--params must be a JSON object, not an array or scalar."""
    from zoho_books_cli.errors import ValidationError

    _setup_auth(in_memory_storage)
    runner = CliRunner()
    result = runner.invoke(app, ["contacts", "list", "--params", "[1,2,3]"])
    assert result.exit_code != 0
    assert isinstance(result.exception, ValidationError)
