import pytest

from zoho_books_cli._uploads import MAX_BYTES, guess_mime, validate
from zoho_books_cli.errors import ValidationError


def test_validate_ok(sample_receipt):
    validate(sample_receipt)


def test_validate_missing_file(tmp_path):
    with pytest.raises(ValidationError):
        validate(tmp_path / "does-not-exist.pdf")


def test_validate_bad_extension(tmp_path):
    bad = tmp_path / "malware.exe"
    bad.write_bytes(b"x")
    with pytest.raises(ValidationError):
        validate(bad)


def test_validate_too_large(tmp_path):
    big = tmp_path / "big.pdf"
    big.write_bytes(b"0" * (MAX_BYTES + 1))
    with pytest.raises(ValidationError):
        validate(big)


def test_guess_mime():
    from pathlib import Path

    assert guess_mime(Path("x.pdf")) == "application/pdf"
    assert guess_mime(Path("x.png")) == "image/png"
