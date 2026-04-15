import pytest

from zoho_books_cli.regions import REGIONS, resolve


def test_resolve_known():
    assert resolve("us").api_url == "https://www.zohoapis.com"
    assert resolve("EU").accounts_url.endswith(".eu")


def test_resolve_default_empty():
    assert resolve("").code == "us"


def test_resolve_unknown_raises():
    with pytest.raises(ValueError):
        resolve("mars")


def test_all_regions_have_https_urls():
    for r in REGIONS.values():
        assert r.accounts_url.startswith("https://")
        assert r.api_url.startswith("https://")
