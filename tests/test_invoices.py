"""Thin-wrapper tests for `zb invoices ...` (CRUD + state + sub-apps)."""

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


# --- top-level CRUD ----------------------------------------------------------


def test_list(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/invoices").mock(
            return_value=httpx.Response(
                200,
                json={
                    "invoices": [{"invoice_id": "I1"}],
                    "page_context": {"page": 1, "has_more_page": False},
                },
            )
        )
        result = runner.invoke(app, ["invoices", "list"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["items"] == [{"invoice_id": "I1"}]


def test_list_query_round_trips(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.get(
            f"{BASE}/invoices",
            params={"organization_id": "123456", "status": "unpaid", "customer_id": "C1"},
        ).mock(return_value=httpx.Response(200, json={"invoices": [], "page_context": {}}))
        result = runner.invoke(
            app,
            [
                "invoices",
                "list",
                "--query",
                "status=unpaid",
                "--query",
                "customer_id=C1",
            ],
        )
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_get(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/invoices/I1").mock(
            return_value=httpx.Response(200, json={"invoice": {"invoice_id": "I1"}})
        )
        result = runner.invoke(app, ["invoices", "get", "I1"])
    assert result.exit_code == 0, result.stderr


def test_create_preserves_large_ids(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    big = 9820000005670010000
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/invoices").mock(
            return_value=httpx.Response(201, json={"invoice": {}})
        )
        result = runner.invoke(
            app,
            [
                "invoices",
                "create",
                "--body",
                f'{{"customer_id": {big}, "line_items": []}}',
            ],
        )
    assert result.exit_code == 0, result.stderr
    outgoing = json.loads(route.calls[0].request.content)
    assert outgoing["customer_id"] == big


def test_update(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.put(f"{BASE}/invoices/I1").mock(
            return_value=httpx.Response(200, json={"invoice": {}})
        )
        result = runner.invoke(app, ["invoices", "update", "I1", "--body", '{"notes": "n"}'])
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_update_by_custom_field_sets_headers(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.put(f"{BASE}/invoices").mock(
            return_value=httpx.Response(200, json={"invoice": {}})
        )
        result = runner.invoke(
            app,
            [
                "invoices",
                "update-by-custom-field",
                "--key",
                "cf_external_id",
                "--value",
                "abc",
                "--body",
                '{"notes": "n"}',
            ],
        )
    assert result.exit_code == 0, result.stderr
    h = route.calls[0].request.headers
    assert h["X-Unique-Identifier-Key"] == "cf_external_id"
    assert h["X-Unique-Identifier-Value"] == "abc"
    assert "X-Upsert" not in h


def test_update_by_custom_field_upsert_header(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.put(f"{BASE}/invoices").mock(
            return_value=httpx.Response(200, json={"invoice": {}})
        )
        result = runner.invoke(
            app,
            [
                "invoices",
                "update-by-custom-field",
                "--key",
                "cf_external_id",
                "--value",
                "abc",
                "--upsert",
                "--body",
                '{"customer_id": "C1"}',
            ],
        )
    assert result.exit_code == 0, result.stderr
    assert route.calls[0].request.headers["X-Upsert"] == "true"


def test_delete(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.delete(f"{BASE}/invoices/I1").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "deleted"})
        )
        result = runner.invoke(app, ["invoices", "delete", "I1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["invoice_id"] == "I1"


# --- state actions -----------------------------------------------------------


def test_mark_sent(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/invoices/I1/status/sent").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "sent"})
        )
        result = runner.invoke(app, ["invoices", "mark-sent", "I1"])
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_mark_void(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/invoices/I1/status/void").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "voided"})
        )
        result = runner.invoke(app, ["invoices", "mark-void", "I1"])
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_mark_draft(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/invoices/I1/status/draft").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "drafted"})
        )
        result = runner.invoke(app, ["invoices", "mark-draft", "I1"])
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_write_off(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/invoices/I1/writeoff").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "written off"})
        )
        result = runner.invoke(app, ["invoices", "write-off", "I1"])
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_cancel_write_off(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/invoices/I1/writeoff/cancel").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "cancelled"})
        )
        result = runner.invoke(app, ["invoices", "cancel-write-off", "I1"])
    assert result.exit_code == 0, result.stderr
    assert route.called


def test_email(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/invoices/I1/email").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "sent"})
        )
        result = runner.invoke(
            app, ["invoices", "email", "I1", "--body", '{"subject": "Reminder"}']
        )
    assert result.exit_code == 0, result.stderr
    assert json.loads(route.calls[0].request.content) == {"subject": "Reminder"}


def test_email_default_body(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/invoices/I1/email").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "sent"})
        )
        result = runner.invoke(app, ["invoices", "email", "I1"])
    assert result.exit_code == 0, result.stderr
    assert route.calls[0].request.content == b""


def test_email_query_round_trips(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(
            f"{BASE}/invoices/I1/email",
            params={"organization_id": "123456", "send_attachment": "true"},
        ).mock(return_value=httpx.Response(200, json={"code": 0, "message": "sent"}))
        result = runner.invoke(app, ["invoices", "email", "I1", "--query", "send_attachment=true"])
    assert result.exit_code == 0, result.stderr
    assert route.called


# --- reminders sub-app -------------------------------------------------------


def test_reminders_send(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/invoices/I1/paymentreminder").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "reminded"})
        )
        result = runner.invoke(app, ["invoices", "reminders", "send", "I1"])
    assert result.exit_code == 0, result.stderr
    assert route.called


# --- payments sub-app --------------------------------------------------------


def test_payments_list(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/invoices/I1/payments").mock(
            return_value=httpx.Response(
                200,
                json={"payments": [{"payment_id": "P1"}], "page_context": {}},
            )
        )
        result = runner.invoke(app, ["invoices", "payments", "list", "I1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["items"] == [{"payment_id": "P1"}]


# --- credits sub-app ---------------------------------------------------------


def test_credits_list(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/invoices/I1/creditsapplied").mock(
            return_value=httpx.Response(
                200,
                json={"credits": [{"credit_id": "K1"}], "page_context": {}},
            )
        )
        result = runner.invoke(app, ["invoices", "credits", "list", "I1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["items"] == [{"credit_id": "K1"}]


def test_credits_apply_preserves_large_ids(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    big = 9820000005670010000
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/invoices/I1/credits").mock(
            return_value=httpx.Response(201, json={"credits": []})
        )
        result = runner.invoke(
            app,
            [
                "invoices",
                "credits",
                "apply",
                "I1",
                "--body",
                f'{{"apply_creditnotes":[{{"creditnote_id":{big},"amount_applied":50}}]}}',
            ],
        )
    assert result.exit_code == 0, result.stderr
    outgoing = json.loads(route.calls[0].request.content)
    assert outgoing["apply_creditnotes"][0]["creditnote_id"] == big


def test_credits_delete(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.delete(f"{BASE}/invoices/I1/creditsapplied/K1").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "deleted"})
        )
        result = runner.invoke(app, ["invoices", "credits", "delete", "I1", "K1"])
    assert result.exit_code == 0, result.stderr
    assert route.called
    payload = json.loads(result.stdout)
    assert payload["data"]["credit_id"] == "K1"


# --- comments sub-app --------------------------------------------------------


def test_comments_list(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/invoices/I1/comments").mock(
            return_value=httpx.Response(
                200, json={"comments": [{"comment_id": "C1"}], "page_context": {}}
            )
        )
        result = runner.invoke(app, ["invoices", "comments", "list", "I1"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["items"] == [{"comment_id": "C1"}]


def test_comments_add(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/invoices/I1/comments").mock(
            return_value=httpx.Response(201, json={"comment": {"comment_id": "C2"}})
        )
        result = runner.invoke(
            app,
            ["invoices", "comments", "add", "I1", "--body", '{"description": "Note"}'],
        )
    assert result.exit_code == 0, result.stderr
    assert json.loads(route.calls[0].request.content) == {"description": "Note"}


def test_comments_delete(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.delete(f"{BASE}/invoices/I1/comments/C1").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "deleted"})
        )
        result = runner.invoke(app, ["invoices", "comments", "delete", "I1", "C1"])
    assert result.exit_code == 0, result.stderr
    assert route.called


# --- documents sub-app -------------------------------------------------------


def test_documents_get(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/invoices/I1/documents/D1").mock(
            return_value=httpx.Response(200, json={"document": {"document_id": "D1"}})
        )
        result = runner.invoke(app, ["invoices", "documents", "get", "I1", "D1"])
    assert result.exit_code == 0, result.stderr


def test_documents_download_pdf(in_memory_storage, tmp_path):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    out = tmp_path / "doc.pdf"
    body = b"%PDF-1.4\n%downloaded fake content\n"
    with respx.mock() as mock:
        route = mock.get(
            f"{BASE}/invoices/I1/documents/D1",
            params={"organization_id": "123456", "responseformat": "pdf"},
        ).mock(
            return_value=httpx.Response(
                200, content=body, headers={"content-type": "application/pdf"}
            )
        )
        result = runner.invoke(
            app,
            ["invoices", "documents", "download", "I1", "D1", "--output", str(out)],
        )
    assert result.exit_code == 0, result.stderr
    assert route.called
    assert out.read_bytes() == body
    payload = json.loads(result.stdout)
    assert payload["data"]["format"] == "pdf"
    assert payload["data"]["size_bytes"] == len(body)


def test_documents_download_html(in_memory_storage, tmp_path):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    out = tmp_path / "doc.html"
    body = b"<html><body>invoice</body></html>"
    with respx.mock() as mock:
        mock.get(
            f"{BASE}/invoices/I1/documents/D1",
            params={"organization_id": "123456", "responseformat": "html"},
        ).mock(
            return_value=httpx.Response(200, content=body, headers={"content-type": "text/html"})
        )
        result = runner.invoke(
            app,
            [
                "invoices",
                "documents",
                "download",
                "I1",
                "D1",
                "--output",
                str(out),
                "--format",
                "html",
            ],
        )
    assert result.exit_code == 0, result.stderr
    assert out.read_bytes() == body


def test_documents_download_rejects_bad_format(in_memory_storage, tmp_path):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    out = tmp_path / "doc.xyz"
    result = runner.invoke(
        app,
        [
            "invoices",
            "documents",
            "download",
            "I1",
            "D1",
            "--output",
            str(out),
            "--format",
            "xml",
        ],
    )
    assert result.exit_code != 0
    assert not out.exists()


def test_documents_delete(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.delete(f"{BASE}/invoices/I1/documents/D1").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "deleted"})
        )
        result = runner.invoke(app, ["invoices", "documents", "delete", "I1", "D1"])
    assert result.exit_code == 0, result.stderr
    assert route.called


# --- templates sub-app -------------------------------------------------------


def test_templates_list(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.get(f"{BASE}/invoices/templates").mock(
            return_value=httpx.Response(
                200,
                json={"templates": [{"template_id": "T1"}], "page_context": {}},
            )
        )
        result = runner.invoke(app, ["invoices", "templates", "list"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["data"]["items"] == [{"template_id": "T1"}]


def test_templates_apply(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.put(f"{BASE}/invoices/I1/templates/T1").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "applied"})
        )
        result = runner.invoke(app, ["invoices", "templates", "apply", "I1", "T1"])
    assert result.exit_code == 0, result.stderr
    assert route.called


# --- attachments sub-app -----------------------------------------------------


def test_attachments_add(in_memory_storage, tmp_path):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    pdf = tmp_path / "po.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%fake")
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/invoices/I1/attachment").mock(
            return_value=httpx.Response(201, json={"code": 0, "message": "attached"})
        )
        result = runner.invoke(app, ["invoices", "attachments", "add", "I1", str(pdf)])
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
        mock.get(f"{BASE}/invoices/I1/attachment").mock(
            return_value=httpx.Response(
                200, content=body, headers={"content-type": "application/pdf"}
            )
        )
        result = runner.invoke(app, ["invoices", "attachments", "get", "I1", "--output", str(out)])
    assert result.exit_code == 0, result.stderr
    assert out.read_bytes() == body
    payload = json.loads(result.stdout)
    assert payload["data"]["size_bytes"] == len(body)


def test_attachments_get_404_does_not_create_file(in_memory_storage, tmp_path):
    """A 404 must not leave a partial file or pre-create the parent directory."""
    from zoho_books_cli.errors import NotFound

    _setup_auth(in_memory_storage)
    runner = CliRunner()
    out = tmp_path / "missing-subdir" / "downloaded.pdf"
    with respx.mock() as mock:
        mock.get(f"{BASE}/invoices/I1/attachment").mock(
            return_value=httpx.Response(404, json={"code": 1002, "message": "not found"})
        )
        result = runner.invoke(app, ["invoices", "attachments", "get", "I1", "--output", str(out)])
    assert isinstance(result.exception, NotFound)
    assert not out.exists()
    assert not out.parent.exists()


def test_attachments_delete(in_memory_storage):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        route = mock.delete(f"{BASE}/invoices/I1/attachment").mock(
            return_value=httpx.Response(200, json={"code": 0, "message": "deleted"})
        )
        result = runner.invoke(app, ["invoices", "attachments", "delete", "I1"])
    assert result.exit_code == 0, result.stderr
    assert route.called
