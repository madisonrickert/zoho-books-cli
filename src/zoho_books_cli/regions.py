"""Zoho data-center region to domain mapping.

Zoho hosts accounts / API under different TLDs per region. The caller passes a
short region code (e.g. "us", "eu") and we return the accounts + API base URLs.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Region:
    code: str
    accounts_url: str
    api_url: str


REGIONS: dict[str, Region] = {
    "us": Region("us", "https://accounts.zoho.com", "https://www.zohoapis.com"),
    "eu": Region("eu", "https://accounts.zoho.eu", "https://www.zohoapis.eu"),
    "in": Region("in", "https://accounts.zoho.in", "https://www.zohoapis.in"),
    "au": Region("au", "https://accounts.zoho.com.au", "https://www.zohoapis.com.au"),
    "jp": Region("jp", "https://accounts.zoho.jp", "https://www.zohoapis.jp"),
    "ca": Region("ca", "https://accounts.zohocloud.ca", "https://www.zohoapis.ca"),
    "sa": Region("sa", "https://accounts.zoho.sa", "https://www.zohoapis.sa"),
}


def resolve(code: str) -> Region:
    code = (code or "us").lower().strip()
    if code not in REGIONS:
        raise ValueError(f"Unknown region {code!r}. Valid: {', '.join(sorted(REGIONS))}")
    return REGIONS[code]
