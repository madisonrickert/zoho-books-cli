# zoho-books-cli

**An agent-first command-line interface for [Zoho Books](https://www.zoho.com/books/)**

[![CI](https://github.com/madisonrickert/zoho-books-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/madisonrickert/zoho-books-cli/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Rust](https://img.shields.io/badge/rust-1.85%2B-blue.svg)](https://www.rust-lang.org)

> **Upgrading from a Python 0.5.x install?** See [`MIGRATION.md`](MIGRATION.md). The binary name (`zb`), command surface, JSON envelopes, and stored credentials are unchanged — the migration is one `uv tool uninstall` + one `brew install`.

Designed for AI agents and shell-scripted automation — Claude, ChatGPT, cron jobs, anything that can invoke a binary. Pair it with the [Zoho MCP server](https://mcp.zoho.com) for AI conveniences (full-text search, suggestions); reach for `zb` whenever:

- **You're moving binary files.** Upload or download receipts, bill / invoice attachments, bank-statement imports, and document PDFs directly. MCP's JSON-RPC transport can't carry file bodies; `zb` does native multipart with client-side validation.
- **Response IDs flow into JavaScript.** Zoho's 19-digit IDs exceed `Number.MAX_SAFE_INTEGER`. `zb` keeps every ID as a string end-to-end so JS consumers don't silently corrupt them.
- **You need first-class verbs for state and two-step workflows.** `mark-sent` / `mark-void` / `write-off` on invoices; `mark-void` / `mark-open` / `email` on bills; `apply` / `unapply` for credits and bill payments; `stop` / `resume` on recurring records; `match` / `categorize` / `exclude` / `restore` on bank transactions; `add` / `invite` / `update` for project users; addresses and contact persons; bank account rules. (Coverage is broad but not exhaustive — see "Not yet wrapped" below for what still routes through `zb raw`.)
- **You want pipelines, not prose.** One-line JSON by default, stable exit codes, opt-in CSV / YAML / NDJSON streaming (`--page-all`), `--dry-run` previews, `--params '{JSON}'` for agent-friendly query construction.
- **You want a slim per-turn token footprint.** Against the same Zoho MCP catalog served through a modern MCP client with tool discovery enabled (Claude Code's Tool Search, the current default), `zb`'s **total surface tax** — the catalog + skill bytes the agent carries every turn — came in ~28% slimmer in our snapshot. Both surfaces are tunable; audit the methodology and re-run against your own configuration in [`bench/`](bench/).

Anything not yet wrapped is reachable via `zb raw <METHOD> <path>`, so the CLI never blocks an agent mid-workflow.

```bash
# attach a scanned receipt to an expense (a binary upload MCP can't carry)
zb expenses receipt upload 9820000005670010000 ~/Downloads/starbucks.pdf

# email an invoice with the PDF attached
zb invoices email 9820000009999001000 --query send_attachment=true

# apply a credit-note to an invoice
zb invoices credits apply 9820000009999001000 --body '{"apply_creditnotes":[{"creditnote_id":"9820000001234001000","amount_applied":100}]}'

# preview a destructive call without sending it — no network, no token refresh
zb --dry-run customer-payments update 9820000005670010000 --body '{"amount":100,"reference_number":"check-1234"}'
```

> **Primary consumer:** AI agents. Default output is JSON; errors are structured; exit codes are meaningful. See [`skills/zoho-books/SKILL.md`](skills/zoho-books/SKILL.md) for the agent-user contract and [`AGENTS.md`](AGENTS.md) for the contributor guide.

## Install

Recommended on macOS: **Homebrew tap.**

```bash
brew install madisonrickert/tap/zoho-books-cli
```

Upgrade with `brew upgrade madisonrickert/tap/zoho-books-cli`; remove with `brew uninstall madisonrickert/tap/zoho-books-cli`.

<details>
<summary>Alternative: cargo install --git</summary>

If you already have a Rust toolchain (`rustup`):

```bash
cargo install --git https://github.com/madisonrickert/zoho-books-cli
```

Re-run the same command to upgrade. Removes with `cargo uninstall zoho-books-cli`.

</details>

<details>
<summary>Alternative: pre-built binaries</summary>

Each release on [GitHub Releases](https://github.com/madisonrickert/zoho-books-cli/releases) ships pre-compiled binaries for macOS arm64, macOS x86_64, and Linux x86_64. Download the tarball for your platform and drop the `zb` binary into a directory on your `$PATH` (e.g. `/usr/local/bin` or `~/.local/bin`).

</details>

## Authentication

1. Go to the [Zoho API Console](https://api-console.zoho.com/) and create a **Server-based Application**.
2. Set the redirect URI to `http://localhost:8976/callback`.
3. Note the **Client ID** and **Client Secret**.
4. Run:

   ```bash
   zb auth login --client-id $ZOHO_CLIENT_ID --client-secret $ZOHO_CLIENT_SECRET
   ```

   A browser window opens; authorize the app. Tokens are stored in your OS keychain (macOS Keychain on Darwin; Secret Service on Linux) with a `0600` file fallback at:
   - macOS: `~/Library/Application Support/zoho-books-cli/credentials.json`
   - Linux: `~/.config/zoho-books-cli/credentials.json`

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
zb expenses receipt upload 9820000005670010000 ~/Downloads/starbucks.pdf
```

Output:

```json
{"ok": true, "data": {"expense_id": "9820000005670010000", "uploaded": "starbucks.pdf", "response": {...}}}
```

### Attach multiple supporting files

```bash
zb expenses attachments add 9820000005670010000 invoice.pdf screenshot.png
zb bills attachments add 9820000001234001000 vendor-contract.pdf
zb invoices attachments add 9820000009999001000 signed-po.pdf
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

**Pass IDs as strings in `--body` JSON when downstream consumers will see them.** The CLI itself preserves them either way (request bodies go through `serde_json`'s `RawValue` so digit sequences reach the wire byte-perfect), but Zoho's 19-digit IDs exceed JavaScript's `Number.MAX_SAFE_INTEGER` and any JS consumer that re-parses the response will silently corrupt them. Quoting at the source avoids the foot-gun. See the [agent-user contract in `SKILL.md`](skills/zoho-books/SKILL.md#ids-must-be-strings-in---body-json) for the full rationale.

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

## Command groups

```bash
zb --list-commands       # authoritative tree as JSON — always current
zb <group> --help        # per-group help
```

Top-level groups:

- `auth` — login / status / refresh / logout
- `org` — list / use / current / get / update
- `expenses`, `recurring-expenses` — CRUD + receipts + attachments + comments + stop/resume
- `bank-transactions`, `bank-rules` — CRUD + match/categorize/exclude/restore + 8-target categorize verbs + statement import + rules CRUD
- `bills` — CRUD + mark-void / mark-open / email + payments apply/unapply + comments + attachments add/get/delete
- `invoices`, `recurring-invoices` — CRUD + state (mark-sent / mark-void / mark-draft / write-off / cancel-write-off) + email + reminders + credits apply/unapply + comments + documents get/download/delete + attachments + templates list/apply
- `customer-payments` — CRUD + refunds CRUD
- `projects` — CRUD + clone + state + invoices list + users / tasks / comments sub-apps
- `contacts` — CRUD + search + state + comments + addresses sub-app + persons sub-app
- `chart-of-accounts` — CRUD + state + transactions list / delete
- `raw` — escape hatch to any Zoho v3 endpoint

The full per-command list with arguments and help text comes from `zb --list-commands`. The agent-user contract — output shapes, error codes, idempotency notes, end-to-end flows — lives in [`skills/zoho-books/SKILL.md`](skills/zoho-books/SKILL.md).

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

The repo ships a Claude Code skill at [`skills/zoho-books/SKILL.md`](skills/zoho-books/SKILL.md). It teaches an agent when to reach for this CLI (vs. Zoho MCP), how to check preconditions, how to parse the JSON contract, and how to handle per-error-code behaviors.

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

The CLI wraps a broad slice of the Zoho Books v3 API but does **not** cover all of it.

**Whole resources still on `zb raw` only:**

- `/items` (item catalog)
- `/estimates`, `/retainerinvoices`
- `/creditnotes`, `/vendorcredits`
- `/vendorpayments` (the record itself; we have `bills payments apply` for the application)
- `/purchaseorders`, `/salesorders`
- `/journals` (manual journal entries)
- `/bankaccounts` top-level CRUD (we have rules + statement import, not the accounts themselves)
- `/timeentries` (project time-tracking entries)
- `/users` (org users), `/taxes`, `/currencies`, `/settings/*`

**Within wrapped surfaces, gaps still routing through `zb raw`:**

- Bills: `submit-for-approval`, `approve`, billing-address edit
- Invoices: customer-statements email, billing-address edit
- Contacts: 1099 tracking, portal/reminder toggles, statements-email, opening balance
- Recurring expenses / invoices: anything beyond what's listed in the command groups above

If one of these is blocking you, open an issue or wrap it locally — `src/commands/common.rs` plus the existing module patterns make it ~50 lines per CRUD surface. In the meantime: `zb raw <METHOD> <path>` reaches anything authenticated.
