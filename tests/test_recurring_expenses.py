"""Thin-wrapper tests for `zb recurring-expenses ...`.

Verifies base path is /recurringexpenses (no hyphen), stop/resume use POST on
/status/{stop,resume}, and children/history use /expenses and /comments.
"""

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
        mock.get(f"{BASE}/recurringexpenses").mock(
            return_value=httpx.Response(
                200,
                json={
                    "recurring_expenses": [{"recurring_expense_id": "R1"}],
                    "page_context": {"page": 1, "has_more_page": False},
                },
            )
        )
        result = runner.invoke(app, ["recurring-expenses", "list"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["items"] == [{"recurring_expense_id": "R1"}]


def test_get(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/recurringexpenses/R1").mock(
            return_value=httpx.Response(200, json={"recurring_expense": {"recurring_expense_id": "R1"}})
        )
        result = runner.invoke(app, ["recurring-expenses", "get", "R1"])
    assert result.exit_code == 0, result.stderr


def test_create_posts_body(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/recurringexpenses").mock(
            return_value=httpx.Response(201, json={"recurring_expense": {"recurring_expense_id": "NEW"}})
        )
        result = runner.invoke(
            app,
            ["recurring-expenses", "create", "--body", '{"account_id": "9820000005670010000"}'],
        )
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_stop_uses_post_on_status_stop_path(in_memory_storage):
    """Regression guard: stop/resume are POST on /status/{stop,resume}, not PUT."""
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/recurringexpenses/R1/status/stop").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "stopped"})
        )
        result = runner.invoke(app, ["recurring-expenses", "stop", "R1"])
    assert result.exit_code == 0, result.stderr
    assert route.called
    assert route.calls[0].request.method == "POST"


def test_resume_uses_post_on_status_resume_path(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/recurringexpenses/R1/status/resume").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "resumed"})
        )
        result = runner.invoke(app, ["recurring-expenses", "resume", "R1"])
    assert result.exit_code == 0, result.stderr
    assert route.called
    assert route.calls[0].request.method == "POST"


def test_children_hits_expenses_subpath(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/recurringexpenses/R1/expenses").mock(
            return_value=httpx.Response(
                200,
                json={"expenses": [{"expense_id": "E1"}], "page_context": {}},
            )
        )
        result = runner.invoke(app, ["recurring-expenses", "children", "R1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["items"] == [{"expense_id": "E1"}]


def test_history_hits_comments_subpath(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/recurringexpenses/R1/comments").mock(
            return_value=httpx.Response(
                200,
                json={"comments": [{"comment_id": "C1"}]},
            )
        )
        result = runner.invoke(app, ["recurring-expenses", "history", "R1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["items"] == [{"comment_id": "C1"}]


def test_update_by_custom_field_sends_headers(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.put(f"{BASE}/recurringexpenses").mock(
            return_value=httpx.Response(200, json={"recurring_expense": {"recurring_expense_id": "R1"}})
        )
        result = runner.invoke(
            app,
            [
                "recurring-expenses",
                "update-by-custom-field",
                "--key",
                "cf_unique",
                "--value",
                "UV1",
                "--body",
                '{"total": 42.0}',
                "--upsert",
            ],
        )
    assert result.exit_code == 0, result.stderr
    req = route.calls[0].request
    assert req.headers["X-Unique-Identifier-Key"] == "cf_unique"
    assert req.headers["X-Unique-Identifier-Value"] == "UV1"
    assert req.headers["X-Upsert"] == "true"


def test_delete(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.delete(f"{BASE}/recurringexpenses/R1").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "deleted"})
        )
        result = runner.invoke(app, ["recurring-expenses", "delete", "R1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["recurring_expense_id"] == "R1"
