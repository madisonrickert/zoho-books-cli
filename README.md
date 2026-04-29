# zoho-books-cli

**An agent-first command-line interface for [Zoho Books](https://www.zoho.com/books/) — built to complement the official MCP server where it can't reach.**

[![CI](https://github.com/madisonrickert/zoho-books-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/madisonrickert/zoho-books-cli/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue.svg)](https://www.python.org)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Designed for AI agents and shell-scripted automation — Claude, ChatGPT, cron jobs, anything that can invoke a binary. Pair it with the [Zoho MCP server](https://mcp.zoho.com) for AI conveniences (full-text search, suggestions); reach for `zb` whenever:

- **You're moving binary files.** Upload or download receipts, bill / invoice attachments, bank-statement imports, and document PDFs directly. MCP's JSON-RPC transport can't carry file bodies; `zb` does native multipart with client-side validation.
- **Response IDs flow into JavaScript.** Zoho's 19-digit IDs exceed `Number.MAX_SAFE_INTEGER`. `zb` keeps every ID as a string end-to-end so JS consumers don't silently corrupt them.
- **You need full v3 coverage in one place.** CRUD plus the action verbs — `mark-sent` / `mark-void` / `write-off` on invoices; `mark-void` / `mark-open` / `email` on bills; `apply` / `unapply` for credits and bill payments; `stop` / `resume` for recurring records; `match` / `categorize` / `exclude` / `restore` on bank transactions; `add` / `invite` / `update` for project users; addresses and contact persons on contacts; full bank account rules — across **every surface the Zoho v3 API exposes**.
- **You want pipelines, not prose.** One-line JSON by default, stable exit codes, opt-in CSV / YAML / NDJSON streaming (`--page-all`), `--dry-run` previews, `--params '{JSON}'` for agent-friendly query construction.

Anything not yet wrapped is reachable via `zb raw <METHOD> <path>`, so the CLI never blocks an agent mid-workflow.

```bash
# attach a scanned receipt to an expense (a binary upload MCP can't carry)
zb expenses receipt upload 982000000567001 ~/Downloads/starbucks.pdf

# email an invoice with the PDF attached
zb invoices email 9820000009999001 --query send_attachment=true

# apply a credit-note to an invoice
zb invoices credits apply 9820000009999001 --body '{"apply_creditnotes":[{"creditnote_id":"...","amount_applied":100}]}'

# preview a destructive call without sending it — no network, no token refresh
zb --dry-run customer-payments update P1 --body '{"project_id":"..."}'
```

> **Primary consumer:** AI agents. Default output is JSON; errors are structured; exit codes are meaningful. See [`skills/zoho-books/SKILL.md`](skills/zoho-books/SKILL.md) for the agent-user contract and [`AGENTS.md`](AGENTS.md) for the contributor guide.

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

### Upload a receipt to an expense

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

**IDs must be strings in `--body` JSON** — Zoho IDs exceed JavaScript's safe-integer limit and will lose precision if serialized as numbers. See the [agent-user contract in `SKILL.md`](skills/zoho-books/SKILL.md#ids-must-be-strings-in---body-json) for the full rationale.

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
zb --list-commands         # full machine-readable command tree (JSON)

zb auth login|status|refresh|logout
zb org list|use|current
zb org get <organization_id>
zb org update <organization_id> --body '{...}'

zb expenses list|get|create|update|update-by-custom-field|delete
zb expenses receipt upload|get|delete
zb expenses attachments add|delete
zb expenses comments list

zb recurring-expenses list|get|create|update|update-by-custom-field|delete
zb recurring-expenses stop|resume|children|history

zb bank-transactions list|get|create|update|delete
zb bank-transactions match|matches|unmatch|exclude|restore|uncategorize
zb bank-transactions categorize generic|expense|vendor-payment|customer-payment
zb bank-transactions categorize credit-note-refund|vendor-credit-refund
zb bank-transactions categorize payment-refund|vendor-payment-refund
zb bank-transactions statements import|last-imported|delete

zb bank-rules list|get|create|update|delete

zb bills list|get|create|update|update-by-custom-field|delete
zb bills mark-void|mark-open|email
zb bills payments list|apply|delete
zb bills comments list
zb bills attachments add|get|delete

zb invoices list|get|create|update|update-by-custom-field|delete
zb invoices mark-sent|mark-void|mark-draft
zb invoices write-off|cancel-write-off
zb invoices email
zb invoices reminders send
zb invoices payments list                # read-only; record payments via `customer-payments create`
zb invoices credits list|apply|delete
zb invoices comments list|add|delete
zb invoices documents get|download|delete
zb invoices attachments add|get|delete
zb invoices templates list|apply

zb recurring-invoices list|get|create|update|update-by-custom-field|delete
zb recurring-invoices stop|resume|history
zb recurring-invoices templates apply

zb customer-payments list|get|create|update|update-by-custom-field|delete
zb customer-payments refunds list|get|create|update|delete

zb projects list|get|create|update|update-by-custom-field|delete
zb projects mark-active|mark-inactive|clone|invoices
zb projects users list|get|add|invite|update|delete
zb projects tasks list|get|add|update|delete
zb projects comments list|add|delete

zb contacts list|search|get|create|update|update-by-custom-field|delete
zb contacts mark-active|mark-inactive|comments
zb contacts addresses list|add|update|delete
zb contacts persons list|get|create|update|delete|mark-primary

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

The CLI now covers every surface the Zoho MCP exposes plus several it doesn't (binary uploads/downloads, full bills CRUD, invoice templates, project sub-collections, contact addresses and contact persons, bank account rules). A handful of contact-side niche endpoints (1099 tracking, portal/reminder toggles, statement-email triggers) still need `zb raw` until usage signal warrants a typed wrapper. Anything else missing? Open an issue or use `zb raw <METHOD> <path>` in the meantime.

## Contributing

If you're an AI agent or human contributing code, start with [`AGENTS.md`](AGENTS.md) — it captures the architectural conventions, quality expectations, and review workflow.

## Security

Never commit secrets. See [`SECURITY.md`](SECURITY.md) for disclosure policy and [`.env.example`](.env.example) for configuration.

## License

MIT — see [`LICENSE`](LICENSE).
