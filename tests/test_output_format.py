"""Tests for the --format flag (json, yaml, table, csv) and the --pretty alias."""

from __future__ import annotations

import csv
import io
import json
import time

import httpx
import pytest
import respx
import yaml
from typer.testing import CliRunner

from zoho_books_cli import output
from zoho_books_cli.cli import app
from zoho_books_cli.output import OutputFormat

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


@pytest.fixture(autouse=True)
def _reset_format():
    yield
    output.set_format(OutputFormat.json)
    output.set_dry_run(False)


def test_json_is_default(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/contacts").mock(
            return_value=httpx.Response(
                200,
                json={
                    "contacts": [{"contact_id": "C1", "contact_name": "Acme"}],
                    "page_context": {},
                },
            )
        )
        result = runner.invoke(app, ["contacts", "list"])
    assert result.exit_code == 0, result.stderr
    # Default must be a single-line JSON object.
    assert result.stdout.count("\n") == 1
    payload = json.loads(result.stdout)
    assert payload["data"]["items"][0]["contact_id"] == "C1"


def test_yaml_format(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/contacts").mock(
            return_value=httpx.Response(
                200,
                json={"contacts": [{"contact_id": "C1"}], "page_context": {}},
            )
        )
        result = runner.invoke(app, ["--format", "yaml", "contacts", "list"])
    assert result.exit_code == 0, result.stderr
    loaded = yaml.safe_load(result.stdout)
    assert loaded["ok"] is True
    assert loaded["data"]["items"][0]["contact_id"] == "C1"


def test_csv_on_list_response(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/contacts").mock(
            return_value=httpx.Response(
                200,
                json={
                    "contacts": [
                        {"contact_id": "C1", "contact_name": "Acme", "email": "a@b.com"},
                        {"contact_id": "C2", "contact_name": "Beta", "email": "x@y.com"},
                    ],
                    "page_context": {},
                },
            )
        )
        result = runner.invoke(app, ["--format", "csv", "contacts", "list"])
    assert result.exit_code == 0, result.stderr
    rows = list(csv.DictReader(io.StringIO(result.stdout)))
    assert len(rows) == 2
    assert rows[0]["contact_id"] == "C1"
    assert rows[1]["contact_name"] == "Beta"


def test_csv_on_empty_list_is_empty(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/contacts").mock(
            return_value=httpx.Response(200, json={"contacts": [], "page_context": {}})
        )
        result = runner.invoke(app, ["--format", "csv", "contacts", "list"])
    assert result.exit_code == 0, result.stderr
    assert result.stdout == ""


def test_csv_on_object_response_falls_back_to_json(in_memory_storage):
    """CSV doesn't make sense for a single object; fall back to JSON on stdout."""
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/contacts/C1").mock(
            return_value=httpx.Response(200, json={"contact": {"contact_id": "C1"}})
        )
        result = runner.invoke(app, ["--format", "csv", "contacts", "get", "C1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["contact"]["contact_id"] == "C1"


def test_pretty_alias_still_works(in_memory_storage):
    """--pretty must keep behaving like --format table (rich-rendered JSON)."""
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/contacts").mock(
            return_value=httpx.Response(
                200, json={"contacts": [{"contact_id": "C1"}], "page_context": {}}
            )
        )
        result = runner.invoke(app, ["--pretty", "contacts", "list"])
    assert result.exit_code == 0, result.stderr
    # Rich output is multi-line pretty JSON; must still carry the contact_id.
    assert "C1" in result.stdout
    assert "\n" in result.stdout.rstrip()


def test_format_case_insensitive(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/contacts").mock(
            return_value=httpx.Response(200, json={"contacts": [], "page_context": {}})
        )
        result = runner.invoke(app, ["--format", "YAML", "contacts", "list"])
    assert result.exit_code == 0, result.stderr
    loaded = yaml.safe_load(result.stdout)
    assert loaded["ok"] is True
