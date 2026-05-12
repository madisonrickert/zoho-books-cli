"""Deprecation shim for the Python-era zoho-books-cli install.

This package exists so users who installed `zoho-books-cli` via `uv tool install`
or `pipx install` get a clear migration message on `uv tool upgrade` rather than
an opaque "no installable package" failure. The real CLI is a Rust binary
distributed via Homebrew tap, pre-built GitHub Releases, and `cargo install
--git`. See MIGRATION.md.
"""

__version__ = "0.6.0"
