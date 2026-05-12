"""Entry point for the deprecation shim.

Every invocation prints a JSON envelope (matching the CLI's public contract
shape) to stderr and exits 78 (EX_CONFIG from sysexits.h). Exit 78 is
distinct from the normal Rust-binary exit codes (0-6) so users / agents
can detect "your install is wrong" without confusing it with a real
auth / validation / network error.
"""

from __future__ import annotations

import json
import sys

from zoho_books_cli_legacy import __version__

EXIT_DEPRECATED_INSTALL = 78  # sysexits.h: EX_CONFIG

REPO_URL = "https://github.com/madisonrickert/zoho-books-cli"
MIGRATION_URL = f"{REPO_URL}/blob/main/MIGRATION.md"

MESSAGE = (
    "zoho-books-cli has moved from Python to a single Rust binary as of v1.0.0. "
    "This `uv tool` / `pipx` install is no longer maintained. "
    "Reinstall via: brew install madisonrickert/tap/zoho-books-cli "
    f"(or cargo install --git {REPO_URL}). "
    f"See {MIGRATION_URL} for the full upgrade story."
)


def main() -> None:
    payload = {
        "ok": False,
        "error": {
            "code": "deprecated_install",
            "message": MESSAGE,
            "details": {
                "shim_version": __version__,
                "migration_url": MIGRATION_URL,
                "install_commands": {
                    "homebrew": "brew install madisonrickert/tap/zoho-books-cli",
                    "cargo": f"cargo install --git {REPO_URL}",
                    "github_releases": f"{REPO_URL}/releases/latest",
                },
                "uninstall_first": "uv tool uninstall zoho-books-cli",
            },
        },
    }
    sys.stderr.write(json.dumps(payload) + "\n")
    sys.exit(EXIT_DEPRECATED_INSTALL)


if __name__ == "__main__":
    main()
