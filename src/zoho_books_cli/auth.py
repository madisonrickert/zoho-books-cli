"""Zoho OAuth 2.0: localhost-redirect authorization-code flow + token refresh.

Zoho's OAuth endpoints differ per region — callers pass the region so we build
the right URL. The callback server binds to 127.0.0.1 on a fixed port so the
redirect URI can be registered once in the Zoho API Console.
"""

from __future__ import annotations

import secrets
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, ClassVar

import httpx

from zoho_books_cli.errors import AuthExpired, AuthFailed, NetworkError
from zoho_books_cli.regions import Region

REDIRECT_PORT = 8976
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"
DEFAULT_SCOPES = "ZohoBooks.fullaccess.all"
HTTP_TIMEOUT = 30.0


class _CallbackHandler(BaseHTTPRequestHandler):
    captured: ClassVar[dict[str, str]] = {}
    expected_state: ClassVar[str] = ""

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        params = dict(urllib.parse.parse_qsl(parsed.query))
        if params.get("state") != self.expected_state:
            self._respond(400, "Invalid state. Close this tab and retry `zb auth login`.")
            return
        type(self).captured = params
        if "error" in params:
            self._respond(400, f"Authorization failed: {params.get('error')}")
        else:
            self._respond(
                200,
                "Authorization complete. You can close this tab and return to the terminal.",
            )

    def log_message(self, *args: Any, **kwargs: Any) -> None:  # silence default logging
        pass

    def _respond(self, status: int, body: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))


def authorize(
    *,
    client_id: str,
    client_secret: str,
    region: Region,
    scope: str = DEFAULT_SCOPES,
    open_browser: bool = True,
    timeout_s: float = 300.0,
) -> dict[str, Any]:
    """Run the full authorization-code flow; return the token-exchange response."""

    state = secrets.token_urlsafe(24)
    _CallbackHandler.captured = {}
    _CallbackHandler.expected_state = state

    server = HTTPServer(("127.0.0.1", REDIRECT_PORT), _CallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        auth_url = _build_authorize_url(
            region=region, client_id=client_id, scope=scope, state=state
        )
        if open_browser:
            webbrowser.open(auth_url)
        # Poll for callback up to timeout_s.
        deadline = time.time() + timeout_s
        while time.time() < deadline and not _CallbackHandler.captured:
            time.sleep(0.2)
        if not _CallbackHandler.captured:
            raise AuthFailed(
                "Timed out waiting for OAuth callback.",
                {"authorize_url": auth_url, "timeout_s": timeout_s},
            )
        params = _CallbackHandler.captured
        if "error" in params:
            raise AuthFailed(
                "Authorization denied by Zoho.",
                {"error": params.get("error")},
            )
        code = params.get("code")
        if not code:
            raise AuthFailed("No authorization code returned.", {"params": dict(params)})
        return _exchange_code(
            code=code,
            client_id=client_id,
            client_secret=client_secret,
            region=region,
        )
    finally:
        server.shutdown()
        server.server_close()


def refresh_access_token(
    *,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    region: Region,
) -> dict[str, Any]:
    data = {
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
    }
    try:
        resp = httpx.post(
            f"{region.accounts_url}/oauth/v2/token",
            data=data,
            timeout=HTTP_TIMEOUT,
        )
    except httpx.RequestError as e:
        raise NetworkError(f"Network error during token refresh: {e}") from e
    if resp.status_code != 200:
        raise AuthExpired(
            "Token refresh failed. Re-run `zb auth login`.",
            {"http_status": resp.status_code, "body": _safe_json(resp)},
        )
    body = resp.json()
    if "error" in body:
        raise AuthExpired(
            f"Token refresh rejected: {body.get('error')}",
            {"body": body},
        )
    return body


def _build_authorize_url(*, region: Region, client_id: str, scope: str, state: str) -> str:
    params = {
        "scope": scope,
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{region.accounts_url}/oauth/v2/auth?{urllib.parse.urlencode(params)}"


def _exchange_code(
    *, code: str, client_id: str, client_secret: str, region: Region
) -> dict[str, Any]:
    data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    try:
        resp = httpx.post(
            f"{region.accounts_url}/oauth/v2/token",
            data=data,
            timeout=HTTP_TIMEOUT,
        )
    except httpx.RequestError as e:
        raise NetworkError(f"Network error during token exchange: {e}") from e
    if resp.status_code != 200:
        raise AuthFailed(
            "Token exchange failed.",
            {"http_status": resp.status_code, "body": _safe_json(resp)},
        )
    body = resp.json()
    if "error" in body:
        raise AuthFailed(f"Token exchange rejected: {body.get('error')}", {"body": body})
    return body


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return resp.text
