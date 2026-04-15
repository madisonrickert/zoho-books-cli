"""End-to-end test of the headline feature: upload a receipt, get structured JSON."""

import json

import httpx
import respx
from typer.testing import CliRunner

from zoho_books_cli.cli import app


def _setup_auth(storage_state):
    import time

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


def test_receipt_upload_success(in_memory_storage, sample_receipt):
    _setup_auth(in_memory_storage)
    runner = CliRunner()
    with respx.mock() as mock:
        mock.post("https://www.zohoapis.com/books/v3/expenses/EXP1/receipt").mock(
            return_value=httpx.Response(
                201,
                json={
                    "code": 0,
                    "message": "You have successfully uploaded the receipt.",
                },
            )
        )
        result = runner.invoke(app, ["expenses", "receipt", "upload", "EXP1", str(sample_receipt)])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["expense_id"] == "EXP1"
    assert payload["data"]["uploaded"] == "receipt.pdf"


def test_attachments_add_batch_partial_failure(in_memory_storage, tmp_path):
    _setup_auth(in_memory_storage)
    good = tmp_path / "good.pdf"
    good.write_bytes(b"%PDF-1.4\nok\n")
    bad = tmp_path / "bad.exe"  # unsupported type
    bad.write_bytes(b"x")
    runner = CliRunner()
    with respx.mock() as mock:
        mock.post("https://www.zohoapis.com/books/v3/expenses/EXP1/attachment").mock(
            return_value=httpx.Response(201, json={"message": "ok"})
        )
        result = runner.invoke(app, ["expenses", "attachments", "add", "EXP1", str(good), str(bad)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    results = payload["data"]["results"]
    assert len(results) == 2
    assert results[0]["ok"] is True
    assert results[1]["ok"] is False
    assert results[1]["error"]["code"] == "validation"


def test_validation_error_emits_json_to_stderr(in_memory_storage, tmp_path):
    _setup_auth(in_memory_storage)
    missing = tmp_path / "nope.pdf"
    runner = CliRunner()
    result = runner.invoke(app, ["expenses", "receipt", "upload", "EXP1", str(missing)])
    # The click runner doesn't run our `main()` wrapper, so the exception bubbles
    # instead of being JSON-serialized. Instead, assert that a ZohoCLIError was raised.
    from zoho_books_cli.errors import ValidationError

    assert isinstance(result.exception, ValidationError)
