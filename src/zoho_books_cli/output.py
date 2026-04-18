"""Output helpers: JSON by default, optional --format rendering.

Every command emits exactly one payload to stdout on success, or one to stderr
on error. Default format is line-delimited JSON (`json`) — agents parse stdout
directly. Other formats (`yaml`, `table`, `csv`) are opt-in via the `--format`
root flag. The legacy `--pretty` flag is kept as an alias for `--format table`.

CSV output only renders when the payload is a list-shaped success (a `data`
dict containing an `items` list). Non-list payloads fall back to JSON with a
one-line stderr note so the caller's pipe doesn't silently eat the data.
"""

from __future__ import annotations

import csv as _csv
import io
import json
import sys
from enum import Enum
from typing import Any

_FORMAT: OutputFormat  # set below
_DRY_RUN = False


class OutputFormat(str, Enum):
    json = "json"
    yaml = "yaml"
    table = "table"
    csv = "csv"


_FORMAT = OutputFormat.json


def set_format(value: OutputFormat | str) -> None:
    global _FORMAT
    _FORMAT = value if isinstance(value, OutputFormat) else OutputFormat(value)


def set_pretty(value: bool) -> None:
    """Legacy alias: --pretty -> --format table."""
    if value:
        set_format(OutputFormat.table)


def set_dry_run(value: bool) -> None:
    global _DRY_RUN
    _DRY_RUN = value


def is_dry_run() -> bool:
    return _DRY_RUN


def emit_success(data: Any) -> None:
    _emit({"ok": True, "data": data}, stream=sys.stdout)


def emit_error(payload: dict[str, Any]) -> None:
    _emit(payload, stream=sys.stderr)


def _emit(payload: dict[str, Any], *, stream) -> None:
    if _FORMAT is OutputFormat.json:
        stream.write(json.dumps(payload, default=_default, ensure_ascii=False) + "\n")
    elif _FORMAT is OutputFormat.yaml:
        _write_yaml(payload, stream=stream)
    elif _FORMAT is OutputFormat.table:
        _write_table(payload, stream=stream)
    elif _FORMAT is OutputFormat.csv:
        _write_csv(payload, stream=stream)
    else:  # defensive; enum exhaustive above
        stream.write(json.dumps(payload, default=_default, ensure_ascii=False) + "\n")
    stream.flush()


def _default(obj: Any) -> Any:
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "__fspath__"):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _write_yaml(payload: dict[str, Any], *, stream) -> None:
    import yaml

    # json round-trip first so _default-style coercion applies to datetimes/paths.
    coerced = json.loads(json.dumps(payload, default=_default))
    stream.write(yaml.safe_dump(coerced, sort_keys=False, default_flow_style=False))


def _write_table(payload: dict[str, Any], *, stream) -> None:
    try:
        from rich.console import Console
        from rich.json import JSON
    except ImportError:
        stream.write(json.dumps(payload, indent=2, default=_default) + "\n")
        return
    console = Console(file=stream, soft_wrap=True)
    console.print(JSON(json.dumps(payload, default=_default)))


def _write_csv(payload: dict[str, Any], *, stream) -> None:
    items = _extract_csv_items(payload)
    if items is None:
        sys.stderr.write(
            "zb: --format csv only applies to list responses (data.items[]); "
            "falling back to json.\n"
        )
        stream.write(json.dumps(payload, default=_default, ensure_ascii=False) + "\n")
        return

    if not items:
        return  # empty list → no header, no rows (matches Unix convention)

    keys: list[str] = []
    for item in items:
        if isinstance(item, dict):
            for key in item.keys():
                if key not in keys:
                    keys.append(key)

    buf = io.StringIO()
    writer = _csv.DictWriter(buf, fieldnames=keys, extrasaction="ignore")
    writer.writeheader()
    for item in items:
        if isinstance(item, dict):
            writer.writerow({k: _csv_cell(item.get(k)) for k in keys})
    stream.write(buf.getvalue())


def _extract_csv_items(payload: dict[str, Any]) -> list[Any] | None:
    if not payload.get("ok"):
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    items = data.get("items")
    if not isinstance(items, list):
        return None
    return items


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=_default, ensure_ascii=False)
    return str(value)
