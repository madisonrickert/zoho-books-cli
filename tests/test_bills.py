"""Thin-wrapper tests for `zb bills ...`."""

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
        mock.get(f"{BASE}/bills").mock(
            return_value=httpx.Response(
                200,
                json={
                    "bills": [{"bill_id": "B1"}],
                    "page_context": {"page": 1, "has_more_page": False},
                },
            )
        )
        result = runner.invoke(app, ["bills", "list"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["items"] == [{"bill_id": "B1"}]


def test_get(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/bills/B1").mock(
            return_value=httpx.Response(200, json={"bill": {"bill_id": "B1"}})
        )
        result = runner.invoke(app, ["bills", "get", "B1"])
    assert result.exit_code == 0, result.stderr


def test_create_preserves_large_ids(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    big = 9820000005670010000
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/bills").mock(return_value=httpx.Response(201, json={"bill": {}}))
        result = runner.invoke(
            app,
            [
                "bills",
                "create",
                "--body",
                f'{{"vendor_id": {big}, "line_items": []}}',
            ],
        )
    assert result.exit_code == 0, result.stderr
    outgoing = json.loads(route.calls[0].request.content)
    assert outgoing["vendor_id"] == big


def test_update(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.put(f"{BASE}/bills/B1").mock(
            return_value=httpx.Response(200, json={"bill": {}})
        )
        result = runner.invoke(app, ["bills", "update", "B1", "--body", '{"notes": "updated"}'])
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_update_by_custom_field_sets_headers(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.put(f"{BASE}/bills").mock(return_value=httpx.Response(200, json={"bill": {}}))
        result = runner.invoke(
            app,
            [
                "bills",
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
    assert req.headers["X-Unique-Identifier-Value"] == "abc"
    assert "X-Upsert" not in req.headers


def test_update_by_custom_field_upsert_header(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.put(f"{BASE}/bills").mock(return_value=httpx.Response(200, json={"bill": {}}))
        result = runner.invoke(
            app,
            [
                "bills",
                "update-by-custom-field",
                "--key",
                "cf_external_id",
                "--value",
                "abc",
                "--upsert",
                "--body",
                '{"vendor_id": "V1"}',
            ],
        )
    assert result.exit_code == 0, result.stderr
    assert route.calls[0].request.headers["X-Upsert"] == "true"


def test_list_query_round_trips(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.get(
            f"{BASE}/bills",
            params={"organization_id": "123456", "status": "open", "vendor_id": "V1"},
        ).mock(return_value=httpx.Response(200, json={"bills": [], "page_context": {}}))
        result = runner.invoke(
            app,
            ["bills", "list", "--query", "status=open", "--query", "vendor_id=V1"],
        )
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_delete(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.delete(f"{BASE}/bills/B1").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "deleted"})
        )
        result = runner.invoke(app, ["bills", "delete", "B1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["bill_id"] == "B1"


def test_mark_void(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/bills/B1/status/void").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "voided"})
        )
        result = runner.invoke(app, ["bills", "mark-void", "B1"])
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_mark_open(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/bills/B1/status/open").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "reopened"})
        )
        result = runner.invoke(app, ["bills", "mark-open", "B1"])
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_email_default_body(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/bills/B1/email").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "sent"})
        )
        result = runner.invoke(app, ["bills", "email", "B1"])
    assert result.exit_code == 0, result.stderr
    # No --body passed → no JSON content sent.
    assert route.calls[0].request.content == b""


def test_email_with_body(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/bills/B1/email").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "sent"})
        )
        result = runner.invoke(app, ["bills", "email", "B1", "--body", '{"subject": "Reminder"}'])
    assert result.exit_code == 0, result.stderr
    assert json.loads(route.calls[0].request.content) == {"subject": "Reminder"}


def test_payments_list(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/bills/B1/payments").mock(
            return_value=httpx.Response(
                200,
                json={"payments": [{"bill_payment_id": "P1"}], "page_context": {}},
            )
        )
        result = runner.invoke(app, ["bills", "payments", "list", "B1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["items"] == [{"bill_payment_id": "P1"}]


def test_payments_apply_preserves_large_ids(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    big = 9820000005670010000
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/bills/B1/payments").mock(
            return_value=httpx.Response(201, json={"payment": {}})
        )
        result = runner.invoke(
            app,
            [
                "bills",
                "payments",
                "apply",
                "B1",
                "--body",
                f'{{"bill_payments":[{{"payment_id":{big}}}]}}',
            ],
        )
    assert result.exit_code == 0, result.stderr
    outgoing = json.loads(route.calls[0].request.content)
    assert outgoing["bill_payments"][0]["payment_id"] == big


def test_payments_delete(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.delete(f"{BASE}/bills/B1/payments/P1").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "deleted"})
        )
        result = runner.invoke(app, ["bills", "payments", "delete", "B1", "P1"])
    assert result.exit_code == 0, result.stderr
    assert route.called
    payload = json.loads(result.stdout)
    assert payload["data"]["bill_payment_id"] == "P1"


def test_comments_list(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/bills/B1/comments").mock(
            return_value=httpx.Response(
                200, json={"comments": [{"comment_id": "K1"}], "page_context": {}}
            )
        )
        result = runner.invoke(app, ["bills", "comments", "list", "B1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["items"] == [{"comment_id": "K1"}]


def test_attachments_add(in_memory_storage, tmp_path):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    pdf = tmp_path / "vendor-contract.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%fake")
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/bills/B1/attachment").mock(
            return_value=httpx.Response(201, json={"code": 0, "message": "attached"})
        )
        result = runner.invoke(app, ["bills", "attachments", "add", "B1", str(pdf)])
    assert result.exit_code == 0, result.stderr
    assert route.called
    payload = json.loads(result.stdout)
    assert payload["data"]["results"][0]["ok"] is True


def test_attachments_get_writes_file(in_memory_storage, tmp_path):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    out = tmp_path / "downloaded.pdf"
    body = b"%PDF-1.4\n%downloaded fake content\n"
    with respx.mock() as mock:
        mock.get(f"{BASE}/bills/B1/attachment").mock(
            return_value=httpx.Response(
                200, content=body, headers={"content-type": "application/pdf"}
            )
        )
        result = runner.invoke(app, ["bills", "attachments", "get", "B1", "--output", str(out)])
    assert result.exit_code == 0, result.stderr
    assert out.read_bytes() == body
    payload = json.loads(result.stdout)
    assert payload["data"]["size_bytes"] == len(body)
    assert payload["data"]["content_type"] == "application/pdf"


def test_attachments_get_404_does_not_create_file(in_memory_storage, tmp_path):
    """A 404 on the GET must not leave a partial file or pre-create the parent
    directory. The typed NotFound is raised from get_bytes; callers (e.g.
    `zb` via `main()`) translate that to exit 4 / `code: not_found` per the
    AGENTS.md error contract. Here we assert the in-process behavior:
    NotFound surfaces and no filesystem artifact is created."""
    from zoho_books_cli.errors import NotFound

    _setup_auth(in_memory_storage)
    runner = CliRunner()
    out = tmp_path / "missing-subdir" / "downloaded.pdf"
    with respx.mock() as mock:
        mock.get(f"{BASE}/bills/B1/attachment").mock(
            return_value=httpx.Response(404, json={"code": 1002, "message": "not found"})
        )
        result = runner.invoke(app, ["bills", "attachments", "get", "B1", "--output", str(out)])
    assert isinstance(result.exception, NotFound)
    assert not out.exists()
    assert not out.parent.exists()


def test_attachments_delete(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.delete(f"{BASE}/bills/B1/attachment").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "deleted"})
        )
        result = runner.invoke(app, ["bills", "attachments", "delete", "B1"])
    assert result.exit_code == 0, result.stderr
    assert route.called
