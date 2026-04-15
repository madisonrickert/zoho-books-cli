"""Shared fixtures: isolate tests from real keyring / filesystem / network."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from zoho_books_cli import storage as storage_mod
from zoho_books_cli.config import RuntimeConfig
from zoho_books_cli.regions import resolve


@pytest.fixture
def in_memory_storage(monkeypatch):
    """Replace storage.{load,save,clear} with an in-memory dict."""
    state: dict[str, Any] = {}

    def _load():
        return dict(state) if state else None

    def _save(data):
        state.clear()
        state.update(data)

    def _clear():
        state.clear()

    monkeypatch.setattr(storage_mod, "load", _load)
    monkeypatch.setattr(storage_mod, "save", _save)
    monkeypatch.setattr(storage_mod, "clear", _clear)
    return state


@pytest.fixture
def fake_cfg() -> RuntimeConfig:
    return RuntimeConfig(
        region=resolve("us"),
        org_id="123456",
        client_id="cid",
        client_secret="csec",
        refresh_token="rtok",
        access_token="atok",
        expires_at=time.time() + 3600,
    )


@pytest.fixture
def sample_receipt(tmp_path) -> Path:
    p = tmp_path / "receipt.pdf"
    p.write_bytes(b"%PDF-1.4\n%fake pdf content for tests\n")
    return p
