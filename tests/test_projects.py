"""Thin-wrapper tests for `zb projects ...`."""

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
        mock.get(f"{BASE}/projects").mock(
            return_value=httpx.Response(
                200,
                json={
                    "projects": [{"project_id": "PROJ1"}],
                    "page_context": {"page": 1, "has_more_page": False},
                },
            )
        )
        result = runner.invoke(app, ["projects", "list"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["items"] == [{"project_id": "PROJ1"}]


def test_get(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/projects/PROJ1").mock(
            return_value=httpx.Response(200, json={"project": {"project_id": "PROJ1"}})
        )
        result = runner.invoke(app, ["projects", "get", "PROJ1"])
    assert result.exit_code == 0, result.stderr


def test_create_preserves_large_ids(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    big = 9820000005670010000
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/projects").mock(
            return_value=httpx.Response(201, json={"project": {}})
        )
        result = runner.invoke(
            app,
            [
                "projects",
                "create",
                "--body",
                f'{{"project_name": "X", "customer_id": {big}}}',
            ],
        )
    assert result.exit_code == 0, result.stderr
    outgoing = json.loads(route.calls[0].request.content)
    assert outgoing["customer_id"] == big


def test_update(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.put(f"{BASE}/projects/PROJ1").mock(
            return_value=httpx.Response(200, json={"project": {}})
        )
        result = runner.invoke(
            app, ["projects", "update", "PROJ1", "--body", '{"description": "updated"}']
        )
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_update_by_custom_field_sets_headers(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.put(f"{BASE}/projects").mock(
            return_value=httpx.Response(200, json={"project": {}})
        )
        result = runner.invoke(
            app,
            [
                "projects",
                "update-by-custom-field",
                "--key",
                "cf_external_id",
                "--value",
                "xyz",
                "--body",
                '{"description": "updated"}',
            ],
        )
    assert result.exit_code == 0, result.stderr
    req = route.calls[0].request
    assert req.headers["X-Unique-Identifier-Key"] == "cf_external_id"
    assert req.headers["X-Unique-Identifier-Value"] == "xyz"


def test_delete(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.delete(f"{BASE}/projects/PROJ1").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "deleted"})
        )
        result = runner.invoke(app, ["projects", "delete", "PROJ1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["project_id"] == "PROJ1"


def test_mark_active_posts_active_path(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/projects/PROJ1/active").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "activated"})
        )
        result = runner.invoke(app, ["projects", "mark-active", "PROJ1"])
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_mark_inactive_posts_inactive_path(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/projects/PROJ1/inactive").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "deactivated"})
        )
        result = runner.invoke(app, ["projects", "mark-inactive", "PROJ1"])
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_clone_without_body(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/projects/PROJ1/clone").mock(
            return_value=httpx.Response(201, json={"project": {"project_id": "PROJ2"}})
        )
        result = runner.invoke(app, ["projects", "clone", "PROJ1"])
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_clone_with_body_overrides(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/projects/PROJ1/clone").mock(
            return_value=httpx.Response(201, json={"project": {"project_id": "PROJ2"}})
        )
        result = runner.invoke(
            app, ["projects", "clone", "PROJ1", "--body", '{"project_name": "Cloned"}']
        )
    assert result.exit_code == 0, result.stderr
    outgoing = json.loads(route.calls[0].request.content)
    assert outgoing["project_name"] == "Cloned"


def test_invoices_list(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/projects/PROJ1/invoices").mock(
            return_value=httpx.Response(
                200, json={"invoices": [{"invoice_id": "I1"}], "page_context": {}}
            )
        )
        result = runner.invoke(app, ["projects", "invoices", "PROJ1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["items"] == [{"invoice_id": "I1"}]
