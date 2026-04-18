"""Tests for opt-in auto-pagination via --page-all.

Default behavior (no --page-all) is unchanged: single-page passthrough.
When --page-all is set, list commands loop page=1,2,... emitting one JSON
line per page (NDJSON) until `page_context.has_more_page` is false or
`--page-limit` is hit, whichever comes first.
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


def _pages(items_per_page: list[list[dict]]) -> list[httpx.Response]:
    """Build a sequence of responses with `has_more_page` set correctly per page."""
    out: list[httpx.Response] = []
    for i, items in enumerate(items_per_page):
        has_more = i + 1 < len(items_per_page)
        out.append(
            httpx.Response(
                200,
                json={
                    "contacts": items,
                    "page_context": {"page": i + 1, "has_more_page": has_more},
                },
            )
        )
    return out


def test_default_is_single_page(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.get(f"{BASE}/contacts").mock(
            return_value=httpx.Response(
                200,
                json={
                    "contacts": [{"contact_id": "C1"}],
                    "page_context": {"page": 1, "has_more_page": True},
                },
            )
        )
        result = runner.invoke(app, ["contacts", "list"])
    assert result.exit_code == 0, result.stderr
    assert route.call_count == 1
    assert result.stdout.count("\n") == 1  # exactly one line


def test_page_all_emits_ndjson_until_has_more_is_false(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.get(f"{BASE}/contacts").mock(
            side_effect=_pages(
                [
                    [{"contact_id": "C1"}],
                    [{"contact_id": "C2"}],
                    [{"contact_id": "C3"}],
                ]
            )
        )
        result = runner.invoke(
            app, ["contacts", "list", "--page-all", "--page-delay", "0"]
        )
    assert result.exit_code == 0, result.stderr
    assert route.call_count == 3
    lines = [line for line in result.stdout.strip().split("\n") if line]
    assert len(lines) == 3
    ids = [json.loads(line)["data"]["items"][0]["contact_id"] for line in lines]
    assert ids == ["C1", "C2", "C3"]


def test_page_all_honors_page_limit(in_memory_storage):
    """--page-limit stops the sweep even when Zoho still has more pages."""
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        # has_more_page stays True forever; only --page-limit should stop us.
        def _inf_page(request):
            return httpx.Response(
                200,
                json={
                    "contacts": [{"contact_id": "X"}],
                    "page_context": {"page": 99, "has_more_page": True},
                },
            )

        route = mock.get(f"{BASE}/contacts").mock(side_effect=_inf_page)
        result = runner.invoke(
            app,
            [
                "contacts",
                "list",
                "--page-all",
                "--page-limit",
                "2",
                "--page-delay",
                "0",
            ],
        )
    assert result.exit_code == 0, result.stderr
    assert route.call_count == 2
    lines = [line for line in result.stdout.strip().split("\n") if line]
    assert len(lines) == 2


def test_page_all_starts_at_explicit_page(in_memory_storage):
    """--page N --page-all should begin the sweep at N, not 1."""
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.get(f"{BASE}/contacts").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "contacts": [{"contact_id": "page5"}],
                        "page_context": {"page": 5, "has_more_page": False},
                    },
                ),
            ]
        )
        result = runner.invoke(
            app,
            [
                "contacts",
                "list",
                "--page",
                "5",
                "--page-all",
                "--page-delay",
                "0",
            ],
        )
    assert result.exit_code == 0, result.stderr
    assert route.call_count == 1
    sent = dict(route.calls[0].request.url.params)
    assert sent.get("page") == "5"
