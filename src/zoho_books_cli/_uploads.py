"""Shared helpers for multipart upload commands."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from zoho_books_cli.errors import ValidationError

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".gif"}
MAX_BYTES = 10 * 1024 * 1024  # Zoho's per-attachment limit


def validate(file: Path) -> None:
    if not file.exists():
        raise ValidationError(f"File not found: {file}", {"path": str(file)})
    if not file.is_file():
        raise ValidationError(f"Not a regular file: {file}", {"path": str(file)})
    ext = file.suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            f"Unsupported file type {ext!r}. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
            {"path": str(file), "extension": ext},
        )
    size = file.stat().st_size
    if size > MAX_BYTES:
        raise ValidationError(
            f"File too large ({size} bytes). Max: {MAX_BYTES} bytes (10 MB).",
            {"path": str(file), "size_bytes": size, "max_bytes": MAX_BYTES},
        )


def guess_mime(file: Path) -> str:
    mime, _ = mimetypes.guess_type(file.name)
    return mime or "application/octet-stream"
