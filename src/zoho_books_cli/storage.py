"""Token storage: OS keyring primary, 0600-file fallback.

Stores a single JSON blob under service `zoho-books-cli`, account `credentials`.
Blob schema:

    {
      "client_id": "...",
      "client_secret": "...",
      "refresh_token": "...",
      "access_token": "...",
      "expires_at": 1712345678.0,
      "region": "us"
    }
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir

SERVICE = "zoho-books-cli"
ACCOUNT = "credentials"


def _fallback_path() -> Path:
    return Path(user_config_dir("zoho-books-cli")) / "credentials.json"


def _keyring_available() -> bool:
    try:
        import keyring
        from keyring.backends.fail import Keyring as FailKeyring
    except ImportError:
        return False
    backend = keyring.get_keyring()
    return not isinstance(backend, FailKeyring)


def load() -> dict[str, Any] | None:
    if _keyring_available():
        try:
            import keyring

            raw = keyring.get_password(SERVICE, ACCOUNT)
            if raw:
                return json.loads(raw)
        except Exception:
            pass  # fall through to file
    path = _fallback_path()
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    return None


def save(data: dict[str, Any]) -> None:
    raw = json.dumps(data, ensure_ascii=False)
    if _keyring_available():
        try:
            import keyring

            keyring.set_password(SERVICE, ACCOUNT, raw)
            return
        except Exception:
            pass
    path = _fallback_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write then chmod 0600 to minimize window where file exists with broader perms.
    tmp = path.with_suffix(".tmp")
    tmp.write_text(raw, encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def clear() -> None:
    if _keyring_available():
        try:
            import keyring

            keyring.delete_password(SERVICE, ACCOUNT)
        except Exception:
            pass
    path = _fallback_path()
    if path.exists():
        path.unlink()
