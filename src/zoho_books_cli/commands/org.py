"""`zb org ...` — list, use, current."""

from __future__ import annotations

import typer

from zoho_books_cli import config, output
from zoho_books_cli.errors import ValidationError

app = typer.Typer(help="Manage the default Zoho Books organization.", no_args_is_help=True)


@app.command("list")
def list_orgs():
    """List organizations the authenticated user has access to."""
    cfg = config.load()
    # org_id is not required for /organizations, but the client injects it; we
    # stub it with an empty string and let the client skip injection if missing.
    # Simpler: call the endpoint directly via a bare request bypassing org injection.
    from zoho_books_cli import auth as auth_mod

    config.require_auth(cfg)
    import time

    import httpx

    token = cfg.access_token
    if not token or not cfg.expires_at or cfg.expires_at - 30 <= time.time():
        body = auth_mod.refresh_access_token(
            client_id=cfg.client_id,
            client_secret=cfg.client_secret,
            refresh_token=cfg.refresh_token,
            region=cfg.region,
        )
        token = body["access_token"]
        config.update_access_token(token, time.time() + float(body.get("expires_in", 3600)))

    resp = httpx.get(
        f"{cfg.region.api_url}/books/v3/organizations",
        headers={"Authorization": f"Zoho-oauthtoken {token}"},
        timeout=30,
    )
    data = (
        resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    )
    orgs = data.get("organizations", []) if isinstance(data, dict) else []
    output.emit_success(
        {
            "organizations": [
                {
                    "organization_id": o.get("organization_id"),
                    "name": o.get("name"),
                    "currency_code": o.get("currency_code"),
                    "is_default_org": o.get("is_default_org"),
                }
                for o in orgs
            ]
        }
    )


@app.command("use")
def use(org_id: str = typer.Argument(..., help="Organization ID to store as the default.")):
    """Persist an organization_id as the default for subsequent commands."""
    if not org_id.strip():
        raise ValidationError("org_id is required and must be non-empty.")
    config.save_org(org_id.strip())
    output.emit_success({"org_id": org_id.strip()})


@app.command("current")
def current():
    """Show the currently selected organization_id."""
    cfg = config.load()
    output.emit_success({"org_id": cfg.org_id, "region": cfg.region.code})
