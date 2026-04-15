# Security Policy

## Reporting vulnerabilities

Email **m@madisonrickert.com** with details. Please do not open a public issue for security-sensitive reports.

## Secret handling

This project **never commits credentials**. The following protections are in place:

- `.gitignore` excludes `.env`, `credentials.json`, `*.pem`, and similar patterns.
- [`detect-secrets`](https://github.com/Yelp/detect-secrets) runs as a pre-commit hook and in CI against every push and pull request. A baseline is committed at `.secrets.baseline`.
- OAuth tokens are stored in the OS keyring (macOS Keychain on Darwin) when available, with a `0600`-permission file fallback at `~/.config/zoho-books-cli/credentials.json`.
- Client credentials are **always user-provided at runtime** via `zb auth login --client-id/--client-secret`, environment variables, or interactive prompt. They are never shipped in the package.

If you find a commit that contains a secret, please report it using the email above so we can rotate and scrub the history.
