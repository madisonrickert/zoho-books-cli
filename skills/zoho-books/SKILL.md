---
name: zoho-books
description: Use for any Zoho Books operation — listing/creating/updating/deleting expenses, recurring expenses, bank transactions, customer payments, projects, contacts, or chart-of-accounts entries; categorizing/matching bank transactions; issuing refunds on customer payments; uploading local receipts or attachments. Triggers on phrases like "create an expense in Zoho", "categorize this bank transaction", "find the contact named X", "refund this payment", "mark this project active", "attach this receipt", or any mention of a Zoho Books record ID combined with a CRUD or file operation. Prefer this CLI over the Zoho Books MCP when the user will consume IDs in JavaScript (MCP loses precision on 19-digit IDs) or when uploading local files.
---

# Zoho Books CLI (`zb`)

A thin command-line wrapper over the Zoho Books REST API. Built for agents: outputs JSON on stdout, structured errors on stderr, meaningful exit codes. Preserves 19-digit IDs as strings end-to-end (MCP loses precision in JS runtimes) and handles local binary uploads (MCP can't).

Repo: <https://github.com/madisonrickert/zoho-books-cli>

## When to use this skill vs. the Zoho Books MCP

| Task | Use |
| ---- | --- |
| Upload a local receipt / attachment file | **`zb`** |
| CRUD on expenses, recurring expenses, bank transactions | **`zb`** (IDs preserved as strings) or MCP |
| CRUD on customer payments (and refunds), projects, contacts, chart-of-accounts | **`zb`** (IDs preserved as strings) or MCP |
| Categorize, match, or exclude bank transactions | **`zb`** or MCP |
| Search contacts by name | **`zb contacts search <term>`** |
| CRUD on invoices, bills | Zoho Books MCP (not yet wrapped in `zb`) |
| Project sub-collections (users, tasks, comments) | Zoho Books MCP or `zb raw` |
| Contact sub-collections (addresses, contact persons, 1099 tracking) | Zoho Books MCP or `zb raw` |
| An endpoint neither wraps | `zb raw <METHOD> <path>` |

**Prefer `zb` when** the user is in a JS/Node runtime and needs ID fields intact, or when the operation involves a local file.

## IDs must be strings in --body JSON

Zoho Books IDs are 19 digits. JavaScript's `Number` type starts losing precision at 2^53 − 1 (~16 digits). Whenever you construct `--body` JSON, quote IDs:

```bash
# Correct
zb expenses create --body '{"account_id": "9820000005670010000", "amount": 42.50}'

# Wrong — numeric ID will lose precision in any JS consumer of the response
zb expenses create --body '{"account_id": 9820000005670010000, "amount": 42.50}'
```

## Preconditions

Before any upload, verify the CLI is installed and authenticated:

```bash
zb --version           # confirms install; should print {"ok": true, ...}
zb auth status         # should show {"authenticated": true, ...}
zb org current         # should show a non-null org_id
```

If `auth status` returns `authenticated: false`, stop and tell the user to run `zb auth login --client-id <id> --client-secret <secret>` (you cannot do OAuth on their behalf).

If `org current` returns null, run `zb org list` and ask the user which organization to use, then `zb org use <id>`.

## Core commands

### Thin-wrapper convention

Wrapped commands take one or both of:

- `--query key=value` (repeatable) for URL params; `--page` and `--per-page` are first-class on lists.
- `--body '<json>'` or `--body @path/to/file.json` for request bodies.

No typed per-field flags. Build the JSON body from Zoho's API docs.

### Expenses

```bash
zb expenses list [--query k=v ...] [--page N] [--per-page N]
zb expenses get <expense_id>
zb expenses create --body '{...}'
zb expenses update <expense_id> --body '{...}'
zb expenses update-by-custom-field --body '{...}'
zb expenses delete <expense_id>
zb expenses comments list <expense_id>

# Receipt (single file per expense; REPLACES any existing)
zb expenses receipt upload <expense_id> <file>
zb expenses receipt get <expense_id> --output <path>    # downloads the PDF/image to disk
zb expenses receipt delete <expense_id>

# Attachments (multiple supplementary files; APPENDS)
zb expenses attachments add <expense_id> <file> [<file>...]
zb expenses attachments delete <expense_id>
```

### Recurring expenses

```bash
zb recurring-expenses list [--query ...] [--page N] [--per-page N]
zb recurring-expenses get|create|update|delete <id> ...
zb recurring-expenses stop <id>         # POST /status/stop
zb recurring-expenses resume <id>       # POST /status/resume
zb recurring-expenses children <id>     # child expenses created by this recurrence
zb recurring-expenses history <id>      # history / comments feed
```

### Bank transactions

```bash
zb bank-transactions list|get|create|update|delete ...
zb bank-transactions match <id> --body '{"transactions_to_be_matched": [...]}'
zb bank-transactions matches <id>      # list candidate matches
zb bank-transactions unmatch <id>
zb bank-transactions exclude <id>
zb bank-transactions restore <id>
zb bank-transactions uncategorize <id>

# Categorize family — 8 target types
zb bank-transactions categorize generic              <id> --body '{...}'
zb bank-transactions categorize expense              <id> --body '{...}'
zb bank-transactions categorize vendor-payment       <id> --body '{...}'
zb bank-transactions categorize customer-payment     <id> --body '{...}'
zb bank-transactions categorize credit-note-refund   <id> --body '{...}'
zb bank-transactions categorize vendor-credit-refund <id> --body '{...}'
zb bank-transactions categorize payment-refund       <id> --body '{...}'
zb bank-transactions categorize vendor-payment-refund<id> --body '{...}'

# Statement import (paths span /bankstatements and /bankaccounts; grouped for ergonomics)
zb bank-transactions statements import --body '{...}'
zb bank-transactions statements last-imported <account_id>
zb bank-transactions statements delete <account_id> <statement_id>
```

### Bills and invoices (attachments only, for now)

```bash
zb bills attachments add <bill_id> <file> [<file>...]
zb invoices attachments add <invoice_id> <file> [<file>...]
```

### Customer payments

```bash
zb customer-payments list|get|create|update|delete ...
zb customer-payments update-by-custom-field --key cf_... --value ... --body '{...}'
zb customer-payments refunds list|get|create|update|delete <payment_id> [<refund_id>] ...
```

### Projects

```bash
zb projects list|get|create|update|delete ...
zb projects update-by-custom-field --key cf_... --value ... --body '{...}'
zb projects mark-active <id>
zb projects mark-inactive <id>
zb projects clone <id> [--body '{"project_name": "..."}']
zb projects invoices <id>        # list invoices linked to a project
```

### Contacts

```bash
zb contacts list|get|create|update|delete ...
zb contacts update-by-custom-field --key cf_... --value ... --body '{...}'
zb contacts search <substring>   # GET /contacts?contact_name_contains=<substring>
zb contacts mark-active <id>
zb contacts mark-inactive <id>
zb contacts comments <id>        # read-only activity feed
```

### Chart of accounts

```bash
zb chart-of-accounts list|get|create|update|delete ...
zb chart-of-accounts mark-active|mark-inactive <id>
zb chart-of-accounts transactions list [--query ...]
zb chart-of-accounts transactions delete <transaction_id>

# Useful filter for discovering paid-through (bank/cc) accounts:
zb chart-of-accounts list --query filter_by=AccountType.PaidThrough --per-page 200
```

### Escape hatch

```bash
zb raw <GET|POST|PUT|DELETE> <path> [--query k=v] [--body '<json>'|@file.json] [--file field=path]
```

**File constraints** (validated client-side for fast feedback):
- Types: `.pdf`, `.jpg`, `.jpeg`, `.png`, `.gif`
- Size: ≤ 10 MB per file

## Output contract (stable — parse it directly)

**Success** → stdout, exit 0:

```json
{"ok": true, "data": {...}}
```

**Error** → stderr, non-zero exit:

```json
{"ok": false, "error": {"code": "<code>", "message": "<human>", "details": {...}}}
```

Stable `error.code` values and exit codes:

| `error.code` | Exit | Meaning / Agent response |
| ------------ | ---- | ------------------------ |
| `auth_required` | 2 | Tell user to run `zb auth login`. Do not retry. |
| `auth_expired`  | 2 | Tell user their refresh token was rejected; re-login. |
| `auth_failed`   | 2 | Login/refresh exchange failed; check client_id/secret. |
| `validation`    | 3 | Usually a bad file path, unsupported type, or too-large file. Fix the inputs before retrying. |
| `not_found`     | 4 | The expense/bill/invoice ID doesn't exist. Double-check with MCP. |
| `api_error`     | 4 | Zoho returned 4xx. `details.zoho_code` has Zoho's specific error code. |
| `rate_limited`  | 5 | `details.retry_after_s` tells you how long to wait. |
| `network`       | 6 | Transient. Retry once; if it keeps failing, surface to user. |
| `unknown`       | 1 | Surface to user with the message. |

## Batch upload behavior

`attachments add` with multiple files does **not** abort on the first failure. The response is:

```json
{"ok": true, "data": {"expense_id": "...", "results": [
  {"file": "a.pdf", "ok": true,  "response": {...}},
  {"file": "b.exe", "ok": false, "error": {"code": "validation", ...}}
]}}
```

Always iterate `data.results[]` and report per-file outcomes to the user.

## Typical agent flow (uploading a receipt)

1. User: "Attach `~/Downloads/starbucks.pdf` to expense 982000000567001"
2. Verify preconditions (`zb auth status`, `zb org current`)
3. Run `zb expenses receipt upload 982000000567001 ~/Downloads/starbucks.pdf`
4. Parse the JSON response:
   - `ok: true` → confirm success to the user, include `data.uploaded` filename
   - `ok: false` → surface `error.message`; if `error.code` is `not_found`, offer to list recent expenses via MCP to find the right ID

## Command introspection

If you need to discover commands at runtime (e.g. after a CLI upgrade):

```bash
zb --list-commands
```

Returns the full command tree with each command's name, summary, and parameter list as JSON.

## Full contract reference

See [`AGENTS.md`](https://github.com/madisonrickert/zoho-books-cli/blob/main/AGENTS.md) in the repo for the exhaustive contract.
