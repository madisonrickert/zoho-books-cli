# zoho-books-cli

[![CI](https://github.com/madisonrickert/zoho-books-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/madisonrickert/zoho-books-cli/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue.svg)](https://www.python.org)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

An agent-first command-line interface for [Zoho Books](https://www.zoho.com/books/). Provides coverage of `/expenses`, `/recurringexpenses`, `/banktransactions`, `/customerpayments`, `/projects`, `/contacts`, and `/chartofaccounts`, plus the receipt and attachment binary uploads that the [Zoho Books MCP server](https://www.zoho.com/books/api/) can't do over JSON-RPC. IDs are preserved as strings end-to-end so 19-digit Zoho IDs don't lose precision in JavaScript consumers.

> **Primary consumer:** AI agents. Default output is JSON; errors are structured; exit codes are meaningful. See [`AGENTS.md`](AGENTS.md) for the full contract.

## Install

Using [uv](https://docs.astral.sh/uv/) (recommended):

```bash
# Straight from GitHub
uv tool install git+https://github.com/madisonrickert/zoho-books-cli

# Or from a local checkout
git clone https://github.com/madisonrickert/zoho-books-cli
cd zoho-books-cli
uv tool install .
```

Upgrade with `uv tool upgrade zoho-books-cli`; remove with `uv tool uninstall zoho-books-cli`.

<details>
<summary>Alternative: pipx</summary>

```bash
pipx install git+https://github.com/madisonrickert/zoho-books-cli
# or editable from a clone:
pipx install -e .
```
</details>

## Authentication

1. Go to the [Zoho API Console](https://api-console.zoho.com/) and create a **Server-based Application**.
2. Set the redirect URI to `http://localhost:8976/callback`.
3. Note the **Client ID** and **Client Secret**.
4. Run:

   ```bash
   zb auth login --client-id $ZOHO_CLIENT_ID --client-secret $ZOHO_CLIENT_SECRET
   ```

   A browser window opens; authorize the app. Tokens are stored in your OS keychain (macOS Keychain on Darwin) with a `0600` file fallback at `~/.config/zoho-books-cli/credentials.json`.

5. Pick your organization:

   ```bash
   zb org list
   zb org use <organization_id>
   ```

Scopes requested: `ZohoBooks.fullaccess.all`. For a narrower set, pass `--scope "ZohoBooks.expenses.ALL ZohoBooks.settings.READ"` (sufficient for the attachment workflows).

### Headless / CI

Set these environment variables to skip the browser flow:

```bash
export ZOHO_CLIENT_ID=...
export ZOHO_CLIENT_SECRET=...
export ZOHO_REFRESH_TOKEN=...
export ZOHO_ORG_ID=...
export ZOHO_REGION=us
```

## Usage

### Upload a receipt to an expense (the headline feature)

```bash
zb expenses receipt upload 982000000567001 ~/Downloads/starbucks.pdf
```

Output:

```json
{"ok": true, "data": {"expense_id": "982000000567001", "uploaded": "starbucks.pdf", "response": {...}}}
```

### Attach multiple supporting files

```bash
zb expenses attachments add 982000000567001 invoice.pdf screenshot.png
zb bills attachments add 9820000001234001 vendor-contract.pdf
zb invoices attachments add 9820000009999001 signed-po.pdf
```

### List expenses and bank transactions

```bash
zb expenses list --query status=unfiled --page 1 --per-page 50
zb bank-transactions list --query account_id=9820000005670010000 --per-page 25
```

Every list command is single-page by default and exposes Zoho's `page_context`. Loop on `page_context.has_more_page` if you need more rows — or pass `--page-all` to have the CLI stream pages as NDJSON (one page per line), bounded by `--page-limit` (default 10) and `--page-delay` (default 100ms between requests).

Prefer `--params '{"account_id": "...", "per_page": 50}'` over repeated `--query k=v` when scripting — it's a single JSON object and easier for agents to assemble.

### Create, update, delete

Thin wrappers — pass the body as inline JSON or `@file.json`:

```bash
zb expenses create --body '{"account_id":"9820000005670010000","date":"2026-04-15","amount":42.50}'
zb expenses update EXP1 --body @updates.json
zb expenses delete EXP1
```

**IDs must be strings in `--body` JSON** — Zoho IDs exceed JavaScript's safe-integer limit and will lose precision if serialized as numbers. See [`AGENTS.md`](AGENTS.md#ids-must-be-strings).

### Categorize a bank transaction

```bash
zb bank-transactions categorize expense <txn_id> --body '{"account_id":"..."}'
zb bank-transactions match <txn_id> --body '{"transactions_to_be_matched":[{"transaction_id":"..."}]}'
```

### Escape hatch — any endpoint

```bash
zb raw GET /invoices --query "status=unpaid"
zb raw POST /contacts --body '{"contact_name":"Acme"}'
```

## Command tree

```
zb --list-commands         # machine-readable command tree (JSON)

zb auth login|status|refresh|logout
zb org list|use|current

zb expenses list|get|create|update|update-by-custom-field|delete
zb expenses receipt upload|delete
zb expenses receipt get <expense_id> --output <path>
zb expenses attachments add|delete
zb expenses comments list

zb recurring-expenses list|get|create|update|delete|stop|resume|children|history

zb bank-transactions list|get|create|update|delete
zb bank-transactions match|unmatch|matches|exclude|restore|uncategorize
zb bank-transactions categorize generic|expense|vendor-payment|customer-payment
zb bank-transactions categorize credit-note-refund|vendor-credit-refund
zb bank-transactions categorize payment-refund|vendor-payment-refund
zb bank-transactions statements import --body '{...}'
zb bank-transactions statements last-imported <account_id>
zb bank-transactions statements delete <account_id> <statement_id>

zb bills attachments add|delete
zb invoices attachments add|delete

zb customer-payments list|get|create|update|update-by-custom-field|delete
zb customer-payments refunds list|get|create|update|delete

zb projects list|get|create|update|update-by-custom-field|delete
zb projects mark-active|mark-inactive|clone|invoices

zb contacts list|get|create|update|update-by-custom-field|delete
zb contacts search <term>
zb contacts mark-active|mark-inactive|comments

zb chart-of-accounts list|get|create|update|delete|mark-active|mark-inactive
zb chart-of-accounts transactions list|delete

zb raw <METHOD> <path>
```

## Output contract

All commands print a single JSON object:

- **Success** → stdout: `{"ok": true, "data": {...}}`
- **Error** → stderr: `{"ok": false, "error": {"code": "...", "message": "...", "details": {...}}}`

Pass `--format json|yaml|table|csv` to switch serializers (`json` is default; `--pretty` is a legacy alias for `--format table`). Pass `--dry-run` to print the request that would be sent — method, url, query, body, headers, files — without calling Zoho. Useful for previewing destructive calls.

Exit codes:

| Code | Meaning |
| ---- | ------- |
| `0`  | Success |
| `1`  | Unknown error |
| `2`  | Authentication / credentials |
| `3`  | Validation (bad args, file too large, unsupported type) |
| `4`  | API error (4xx from Zoho) |
| `5`  | Rate-limited (429) |
| `6`  | Network / transport |

## Agent skill

The repo ships a Claude Code skill at [`skills/zoho-books/SKILL.md`](skills/zoho-books/SKILL.md). It teaches an agent when to reach for this CLI (vs. the Zoho Books MCP), how to check preconditions, how to parse the JSON contract, and how to handle per-error-code behaviors.

### Install the skill

Symlink (follows repo updates — recommended if you cloned for dev):

```bash
mkdir -p ~/.claude/skills
ln -s "$(pwd)/skills/zoho-books" ~/.claude/skills/zoho-books
```

Or copy once (no auto-updates):

```bash
mkdir -p ~/.claude/skills
cp -r skills/zoho-books ~/.claude/skills/
```

Or pull straight from GitHub without cloning:

```bash
mkdir -p ~/.claude/skills/zoho-books
curl -fsSL https://raw.githubusercontent.com/madisonrickert/zoho-books-cli/main/skills/zoho-books/SKILL.md \
  -o ~/.claude/skills/zoho-books/SKILL.md
```

Restart Claude Code (or run `/skills` to verify) and the `zoho-books` skill will activate automatically when you ask an agent to attach a file to a Zoho Books record.

## Not yet wrapped

`/bankaccounts/rules`, `/invoices` CRUD, `/bills` CRUD, project sub-collections (users/tasks/comments), contact sub-collections (addresses/contact-persons/1099-tracking), and other surfaces still need `zb raw`. Coming in follow-up releases; contributions welcome.

## Security

Never commit secrets. See [`SECURITY.md`](SECURITY.md) for disclosure policy and [`.env.example`](.env.example) for configuration.

## License

MIT — see [`LICENSE`](LICENSE).
