---
name: zoho-books
description: Use when the user wants to upload a local receipt or attachment file to a Zoho Books expense, bill, or invoice — a gap the Zoho Books MCP server cannot fill because it can't pass local file bytes over JSON-RPC. Triggers on phrases like "attach this receipt", "upload a receipt to the expense", "add an attachment to that bill/invoice in Zoho", or any request that combines a Zoho Books record ID with a local file path. Also use for Zoho Books API operations not wrapped by the MCP server (via `zb raw`).
---

# Zoho Books CLI (`zb`)

A thin command-line wrapper over the Zoho Books REST API. Built for agents: outputs JSON on stdout, structured errors on stderr, meaningful exit codes. Fills gaps in the Zoho Books MCP server — primarily, **uploading local binary files**.

Repo: <https://github.com/madisonrickert/zoho-books-cli>

## When to use this skill vs. the Zoho Books MCP

| Task | Use |
| ---- | --- |
| Upload a local receipt / attachment file | **`zb` (this CLI)** |
| List, get, create, update expenses / invoices / bills / contacts / bank txns | Zoho Books MCP tools |
| An endpoint MCP doesn't wrap | `zb raw <METHOD> <path>` |

If the user's request involves **a file path on disk being sent to Zoho**, reach for this CLI. Otherwise prefer MCP.

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

```bash
# Expense receipt (single image/PDF per expense; REPLACES any existing)
zb expenses receipt upload <expense_id> <file>
zb expenses receipt delete <expense_id>

# Expense attachments (multiple supplementary files; APPENDS)
zb expenses attachments add <expense_id> <file> [<file>...]
zb expenses attachments delete <expense_id> <attachment_id>

# Bill attachments
zb bills attachments add <bill_id> <file> [<file>...]
zb bills attachments delete <bill_id> <attachment_id>

# Invoice attachments
zb invoices attachments add <invoice_id> <file> [<file>...]
zb invoices attachments delete <invoice_id> <attachment_id>

# Escape hatch for anything not wrapped
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
