"""Resolve runtime config from (in order): CLI flags > env vars > stored creds > defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass

from zoho_books_cli import storage
from zoho_books_cli.errors import AuthRequired, ValidationError
from zoho_books_cli.regions import Region, resolve


@dataclass
class RuntimeConfig:
    region: Region
    org_id: str | None
    client_id: str | None
    client_secret: str | None
    refresh_token: str | None
    access_token: str | None
    expires_at: float | None


def load(
    *,
    region_override: str | None = None,
    org_override: str | None = None,
) -> RuntimeConfig:
    stored = storage.load() or {}

    region_code = region_override or os.environ.get("ZOHO_REGION") or stored.get("region") or "us"
    try:
        region = resolve(region_code)
    except ValueError as e:
        raise ValidationError(str(e)) from e

    org_id = org_override or os.environ.get("ZOHO_ORG_ID") or stored.get("org_id")

    return RuntimeConfig(
        region=region,
        org_id=org_id,
        client_id=os.environ.get("ZOHO_CLIENT_ID") or stored.get("client_id"),
        client_secret=os.environ.get("ZOHO_CLIENT_SECRET") or stored.get("client_secret"),
        refresh_token=os.environ.get("ZOHO_REFRESH_TOKEN") or stored.get("refresh_token"),
        access_token=stored.get("access_token"),
        expires_at=stored.get("expires_at"),
    )


def require_auth(cfg: RuntimeConfig) -> None:
    if not (cfg.client_id and cfg.client_secret and cfg.refresh_token):
        raise AuthRequired(
            "No credentials found. Run `zb auth login` or set ZOHO_CLIENT_ID, "
            "ZOHO_CLIENT_SECRET, and ZOHO_REFRESH_TOKEN."
        )


def save_org(org_id: str) -> None:
    data = storage.load() or {}
    data["org_id"] = org_id
    storage.save(data)


def save_tokens(
    *,
    client_id: str,
    client_secret: str,
    access_token: str,
    refresh_token: str,
    expires_at: float,
    region: str,
) -> None:
    data = storage.load() or {}
    data.update(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
            "region": region,
        }
    )
    storage.save(data)


def update_access_token(access_token: str, expires_at: float) -> None:
    data = storage.load() or {}
    data["access_token"] = access_token
    data["expires_at"] = expires_at
    storage.save(data)
