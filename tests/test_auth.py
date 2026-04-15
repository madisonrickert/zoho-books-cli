import httpx
import pytest
import respx

from zoho_books_cli import auth
from zoho_books_cli.errors import AuthExpired
from zoho_books_cli.regions import resolve


def test_refresh_access_token_success():
    with respx.mock() as mock:
        mock.post("https://accounts.zoho.com/oauth/v2/token").mock(
            return_value=httpx.Response(200, json={"access_token": "new", "expires_in": 3600})
        )
        body = auth.refresh_access_token(
            client_id="c",
            client_secret="s",
            refresh_token="r",
            region=resolve("us"),
        )
    assert body["access_token"] == "new"


def test_refresh_access_token_failure_raises_auth_expired():
    with respx.mock() as mock:
        mock.post("https://accounts.zoho.com/oauth/v2/token").mock(
            return_value=httpx.Response(400, json={"error": "invalid_grant"})
        )
        with pytest.raises(AuthExpired):
            auth.refresh_access_token(
                client_id="c",
                client_secret="s",
                refresh_token="r",
                region=resolve("us"),
            )


def test_refresh_access_token_200_with_error_body():
    # Zoho sometimes returns 200 with an embedded error — treat as auth expired.
    with respx.mock() as mock:
        mock.post("https://accounts.zoho.com/oauth/v2/token").mock(
            return_value=httpx.Response(200, json={"error": "invalid_code"})
        )
        with pytest.raises(AuthExpired):
            auth.refresh_access_token(
                client_id="c",
                client_secret="s",
                refresh_token="r",
                region=resolve("us"),
            )
