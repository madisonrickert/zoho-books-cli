import time

import httpx
import pytest
import respx

from zoho_books_cli.client import ZohoBooksClient
from zoho_books_cli.errors import APIError, NotFound


def test_get_injects_organization_id(fake_cfg):
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get(
            "https://www.zohoapis.com/books/v3/expenses",
            params={"organization_id": "123456", "status": "unfiled"},
        ).mock(return_value=httpx.Response(200, json={"expenses": []}))
        with ZohoBooksClient(fake_cfg) as client:
            body = client.get("/expenses", query={"status": "unfiled"})
        assert body == {"expenses": []}
        assert route.called


def test_401_triggers_refresh_and_retry(fake_cfg, in_memory_storage):
    # Pre-populate storage so update_access_token has something to merge into.
    in_memory_storage.update(
        {
            "client_id": "cid",
            "client_secret": "csec",
            "refresh_token": "rtok",
            "region": "us",
        }
    )
    fake_cfg.access_token = "stale"
    fake_cfg.expires_at = time.time() + 3600  # not expired per clock, but server says stale

    with respx.mock() as mock:
        get_route = mock.get("https://www.zohoapis.com/books/v3/expenses/1").mock(
            side_effect=[
                httpx.Response(401, json={"code": 401, "message": "unauthorized"}),
                httpx.Response(200, json={"expense": {"expense_id": "1"}}),
            ]
        )
        refresh_route = mock.post("https://accounts.zoho.com/oauth/v2/token").mock(
            return_value=httpx.Response(200, json={"access_token": "fresh", "expires_in": 3600})
        )
        with ZohoBooksClient(fake_cfg) as client:
            body = client.get("/expenses/1")

    assert body["expense"]["expense_id"] == "1"
    assert refresh_route.called
    assert get_route.call_count == 2


def test_404_raises_not_found(fake_cfg):
    with respx.mock() as mock:
        mock.get("https://www.zohoapis.com/books/v3/expenses/missing").mock(
            return_value=httpx.Response(404, json={"message": "Expense not found"})
        )
        with ZohoBooksClient(fake_cfg) as client, pytest.raises(NotFound) as exc:
            client.get("/expenses/missing")
    assert "not found" in exc.value.message.lower()


def test_429_backs_off_then_succeeds(fake_cfg, monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("zoho_books_cli.client.time.sleep", lambda s: sleeps.append(s))

    with respx.mock() as mock:
        mock.get("https://www.zohoapis.com/books/v3/expenses").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "2"}, json={"message": "slow down"}),
                httpx.Response(200, json={"expenses": []}),
            ]
        )
        with ZohoBooksClient(fake_cfg) as client:
            body = client.get("/expenses")

    assert body == {"expenses": []}
    assert sleeps == [2]


def test_4xx_other_raises_api_error(fake_cfg):
    with respx.mock() as mock:
        mock.post("https://www.zohoapis.com/books/v3/expenses/1/receipt").mock(
            return_value=httpx.Response(400, json={"code": 4000, "message": "Invalid file type"})
        )
        with ZohoBooksClient(fake_cfg) as client, pytest.raises(APIError) as exc:
            client.post(
                "/expenses/1/receipt", files={"receipt": ("r.pdf", b"x", "application/pdf")}
            )
    assert exc.value.details["http_status"] == 400
    assert exc.value.details["zoho_code"] == 4000


def test_multipart_upload_payload_shape(fake_cfg, sample_receipt):
    """The client sends multipart/form-data with the 'receipt' field name."""
    with respx.mock() as mock:
        route = mock.post("https://www.zohoapis.com/books/v3/expenses/E1/receipt").mock(
            return_value=httpx.Response(201, json={"message": "uploaded"})
        )
        with ZohoBooksClient(fake_cfg) as client, sample_receipt.open("rb") as fh:
            files = {"receipt": (sample_receipt.name, fh, "application/pdf")}
            body = client.post("/expenses/E1/receipt", files=files)
        assert body == {"message": "uploaded"}
        req = route.calls[0].request
        ctype = req.headers.get("content-type", "")
        assert ctype.startswith("multipart/form-data")
        assert b'name="receipt"' in req.content
        assert b"receipt.pdf" in req.content


def test_missing_org_id_raises_validation(fake_cfg):
    fake_cfg.org_id = None
    with ZohoBooksClient(fake_cfg) as client, pytest.raises(Exception) as exc:
        client.get("/expenses")
    from zoho_books_cli.errors import ValidationError

    assert isinstance(exc.value, ValidationError)
