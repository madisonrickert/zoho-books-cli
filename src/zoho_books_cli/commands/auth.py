"""`zb auth ...` — login, status, refresh, logout."""

from __future__ import annotations

import time

import typer

from zoho_books_cli import auth as auth_mod
from zoho_books_cli import config, output, storage
from zoho_books_cli.errors import AuthRequired, ValidationError

app = typer.Typer(help="Authenticate to Zoho Books (OAuth 2.0).", no_args_is_help=True)


@app.command("login")
def login(
    client_id: str = typer.Option(
        None,
        "--client-id",
        envvar="ZOHO_CLIENT_ID",
        help="OAuth client ID from the Zoho API Console.",
    ),
    client_secret: str = typer.Option(
        None,
        "--client-secret",
        envvar="ZOHO_CLIENT_SECRET",
        help="OAuth client secret from the Zoho API Console.",
    ),
    region: str = typer.Option(
        "us",
        "--region",
        envvar="ZOHO_REGION",
        help="Zoho data-center region: us, eu, in, au, jp, ca, sa.",
    ),
    scope: str = typer.Option(
        auth_mod.DEFAULT_SCOPES,
        "--scope",
        help="Space-separated OAuth scopes.",
    ),
    no_browser: bool = typer.Option(
        False,
        "--no-browser",
        help="Do not try to open a browser automatically; print the URL instead.",
    ),
):
    """Run the OAuth authorization-code flow and store tokens."""
    if not client_id or not client_secret:
        raise ValidationError(
            "Missing --client-id / --client-secret (or ZOHO_CLIENT_ID / ZOHO_CLIENT_SECRET)."
        )
    from zoho_books_cli.regions import resolve

    region_obj = resolve(region)
    token_response = auth_mod.authorize(
        client_id=client_id,
        client_secret=client_secret,
        region=region_obj,
        scope=scope,
        open_browser=not no_browser,
    )
    expires_at = time.time() + float(token_response.get("expires_in", 3600))
    config.save_tokens(
        client_id=client_id,
        client_secret=client_secret,
        access_token=token_response["access_token"],
        refresh_token=token_response["refresh_token"],
        expires_at=expires_at,
        region=region_obj.code,
    )
    output.emit_success(
        {
            "authenticated": True,
            "region": region_obj.code,
            "expires_at": expires_at,
        }
    )


@app.command("status")
def status():
    """Report whether credentials are present and when the access token expires."""
    stored = storage.load() or {}
    authed = bool(stored.get("refresh_token") and stored.get("client_id"))
    output.emit_success(
        {
            "authenticated": authed,
            "region": stored.get("region"),
            "org_id": stored.get("org_id"),
            "expires_at": stored.get("expires_at"),
        }
    )


@app.command("refresh")
def refresh():
    """Force an access-token refresh using the stored refresh token."""
    cfg = config.load()
    if not (cfg.client_id and cfg.client_secret and cfg.refresh_token):
        raise AuthRequired("No credentials stored. Run `zb auth login`.")
    body = auth_mod.refresh_access_token(
        client_id=cfg.client_id,
        client_secret=cfg.client_secret,
        refresh_token=cfg.refresh_token,
        region=cfg.region,
    )
    expires_at = time.time() + float(body.get("expires_in", 3600))
    config.update_access_token(body["access_token"], expires_at)
    output.emit_success({"refreshed": True, "expires_at": expires_at})


@app.command("logout")
def logout():
    """Clear stored tokens from keyring and config file."""
    storage.clear()
    output.emit_success({"cleared": True})
