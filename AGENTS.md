# AGENTS.md

This file is a concise reference for AI agents using `zoho-books-cli`. Point your agent at this file to learn the full contract without reading every `--help` page.

## What this CLI is for

Filling feature gaps in the Zoho Books MCP server — primarily uploading local binary files (receipts, attachments) to expenses, bills, and invoices. If an operation is well-supported by MCP, prefer MCP.

## Invocation

Binary name: `zb` (primary) or `zoho-books`.

```bash
zb <group> <subcommand> [args...] [--pretty]
```

Run `zb --list-commands` to get the full command tree as JSON:

```json
{
  "ok": true,
  "data": {
    "commands": [
      {"name": "auth login", "args": ["--client-id", "--client-secret"], "summary": "..."},
      {"name": "expenses receipt upload", "args": ["expense_id", "file"], "summary": "..."}
      // ...
    ]
  }
}
```

## Output contract (stable)

**Success** → stdout, exit 0:

```json
{"ok": true, "data": {...}}
```

**Error** → stderr, non-zero exit:

```json
{"ok": false, "error": {"code": "<code>", "message": "<human>", "details": {...}}}
```

`error.code` values (stable):

| Code | Exit | Meaning |
| ---- | ---- | ------- |
| `auth_required` | 2 | No credentials stored. Run `zb auth login`. |
| `auth_expired`  | 2 | Refresh failed. Re-login. |
| `auth_failed`   | 2 | Login/refresh exchange rejected by Zoho. |
| `validation`    | 3 | Bad arguments, missing file, file too large, unsupported type. |
| `not_found`     | 4 | Zoho returned 404. |
| `api_error`     | 4 | Any other 4xx from Zoho. `details.http_status` and `details.zoho_code` included. |
| `rate_limited`  | 5 | 429. `details.retry_after_s` included. |
| `network`       | 6 | DNS/connect/timeout. |
| `unknown`       | 1 | Anything else. |

## Core commands

### Upload a receipt (single image/PDF per expense; replaces existing)

```bash
zb expenses receipt upload <expense_id> <file>
```

`<file>`: PDF, JPG, JPEG, PNG, or GIF. Max 10 MB.

### Add attachments (multiple files; supplementary docs)

```bash
zb expenses attachments add <expense_id> <file> [<file>...]
zb bills attachments add    <bill_id>    <file> [<file>...]
zb invoices attachments add <invoice_id> <file> [<file>...]
```

Batch-upload is per-file: one failure does **not** abort the rest. The JSON result is an array of per-file outcomes, each with `{"file", "ok", "attachment_id"|"error"}`.

### Raw endpoint access

```bash
zb raw <METHOD> <path> [--query k=v ...] [--body @file.json | --body '<json>'] [--file field=path ...]
```

Use this for any Zoho Books v3 endpoint not explicitly wrapped.

## Preconditions to check before using this CLI

1. `zb auth status` returns `{"ok": true, "data": {"authenticated": true}}`.
2. `zb org current` returns a non-null `org_id`.
3. File to upload exists, is readable, is ≤10 MB, and is an allowed type.

If any precondition fails, surface the structured error to the user rather than retrying blindly.

## Idempotency notes

- `receipt upload` **replaces** any existing receipt on the expense.
- `attachments add` **appends** — calling twice with the same file creates two attachments.
- `attachments delete` and `receipt delete` are idempotent; deleting an already-deleted item returns `not_found`.
