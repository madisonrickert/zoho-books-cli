"""Unit tests for commands/_shared.py."""

from __future__ import annotations

import json
from io import StringIO

import pytest

from zoho_books_cli import output
from zoho_books_cli.commands import _shared
from zoho_books_cli.errors import ValidationError


# ---- parse_body -------------------------------------------------------------


def test_parse_body_none_returns_none():
    assert _shared.parse_body(None) is None
    assert _shared.parse_body("") is None


def test_parse_body_inline_json_dict():
    assert _shared.parse_body('{"a": 1}') == {"a": 1}


def test_parse_body_preserves_large_integer_ids():
    # 19-digit ID — well inside Python int range, exceeds JS safe integer.
    big = 9820000005670010000
    body = json.dumps({"expense_id": big, "amount": 42.50})
    parsed = _shared.parse_body(body)
    assert parsed["expense_id"] == big
    assert isinstance(parsed["expense_id"], int)


def test_parse_body_from_file(tmp_path):
    p = tmp_path / "expense.json"
    p.write_text('{"account_id": "9820000005670010000"}', encoding="utf-8")
    assert _shared.parse_body(f"@{p}") == {"account_id": "9820000005670010000"}


def test_parse_body_missing_file_raises_validation(tmp_path):
    with pytest.raises(ValidationError) as exc:
        _shared.parse_body(f"@{tmp_path}/nope.json")
    assert "not found" in exc.value.message.lower()


def test_parse_body_invalid_json_raises_validation():
    with pytest.raises(ValidationError) as exc:
        _shared.parse_body("{not json}")
    assert "valid json" in exc.value.message.lower()


def test_parse_body_invalid_json_in_file_raises_validation(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json}", encoding="utf-8")
    with pytest.raises(ValidationError):
        _shared.parse_body(f"@{p}")


# ---- parse_query_pairs ------------------------------------------------------


def test_parse_query_pairs_empty():
    assert _shared.parse_query_pairs(None) == {}
    assert _shared.parse_query_pairs([]) == {}


def test_parse_query_pairs_basic():
    assert _shared.parse_query_pairs(["status=unfiled", "customer_id=9820000005670010000"]) == {
        "status": "unfiled",
        "customer_id": "9820000005670010000",
    }


def test_parse_query_pairs_preserves_id_strings():
    """ID-shaped values must stay as strings — no integer coercion."""
    out = _shared.parse_query_pairs(["customer_id=9820000005670010000"])
    assert out["customer_id"] == "9820000005670010000"
    assert isinstance(out["customer_id"], str)


def test_parse_query_pairs_value_may_contain_equals():
    assert _shared.parse_query_pairs(["filter=a=b"]) == {"filter": "a=b"}


def test_parse_query_pairs_rejects_missing_equals():
    with pytest.raises(ValidationError):
        _shared.parse_query_pairs(["badpair"])


def test_parse_query_pairs_rejects_empty_key():
    with pytest.raises(ValidationError):
        _shared.parse_query_pairs(["=value"])


# ---- emit_list / emit_object / emit_action ---------------------------------


def _capture_stdout(monkeypatch) -> StringIO:
    buf = StringIO()
    monkeypatch.setattr("sys.stdout", buf)
    output.set_pretty(False)
    return buf


def test_emit_list_strips_envelope_and_exposes_items_and_page_context(monkeypatch):
    buf = _capture_stdout(monkeypatch)
    _shared.emit_list(
        {
            "code": 0,
            "message": "success",
            "expenses": [{"expense_id": "1"}, {"expense_id": "2"}],
            "page_context": {"page": 1, "has_more_page": True},
        },
        "expenses",
    )
    payload = json.loads(buf.getvalue())
    assert payload["ok"] is True
    assert payload["data"]["items"] == [{"expense_id": "1"}, {"expense_id": "2"}]
    assert payload["data"]["page_context"] == {"page": 1, "has_more_page": True}
    assert "code" not in payload["data"]
    assert "message" not in payload["data"]


def test_emit_list_missing_collection_key_returns_empty_items(monkeypatch):
    buf = _capture_stdout(monkeypatch)
    _shared.emit_list({"code": 0, "message": "success"}, "expenses")
    payload = json.loads(buf.getvalue())
    assert payload["data"]["items"] == []


def test_emit_object_strips_envelope(monkeypatch):
    buf = _capture_stdout(monkeypatch)
    _shared.emit_object({"code": 0, "message": "success", "expense": {"expense_id": "E1"}})
    payload = json.loads(buf.getvalue())
    assert payload["data"] == {"expense": {"expense_id": "E1"}}


def test_emit_action_shape(monkeypatch):
    buf = _capture_stdout(monkeypatch)
    _shared.emit_action("expense_id", "E1", {"code": 0, "message": "deleted"})
    payload = json.loads(buf.getvalue())
    assert payload["data"]["expense_id"] == "E1"
    assert payload["data"]["acted"] is True
    assert payload["data"]["response"] == {"code": 0, "message": "deleted"}
