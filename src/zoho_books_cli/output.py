"""Output helpers: JSON by default, optional --pretty rendering.

Every command must emit exactly one JSON object to stdout on success, or one
JSON object to stderr on error. No log lines, no progress bars, no extra text
in the default path — agents parse stdout directly.
"""

from __future__ import annotations

import json
import sys
from typing import Any

_PRETTY = False


def set_pretty(value: bool) -> None:
    global _PRETTY
    _PRETTY = value


def emit_success(data: Any) -> None:
    payload = {"ok": True, "data": data}
    if _PRETTY:
        _print_pretty(payload, stream=sys.stdout)
    else:
        sys.stdout.write(json.dumps(payload, default=_default, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def emit_error(payload: dict[str, Any]) -> None:
    if _PRETTY:
        _print_pretty(payload, stream=sys.stderr)
    else:
        sys.stderr.write(json.dumps(payload, default=_default, ensure_ascii=False) + "\n")
        sys.stderr.flush()


def _default(obj: Any) -> Any:
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "__fspath__"):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _print_pretty(payload: dict[str, Any], *, stream) -> None:
    try:
        from rich.console import Console
        from rich.json import JSON
    except ImportError:
        stream.write(json.dumps(payload, indent=2, default=_default) + "\n")
        stream.flush()
        return
    console = Console(file=stream, soft_wrap=True)
    console.print(JSON(json.dumps(payload, default=_default)))
