---
name: zoho-books
description: Use for any Zoho Books operation — listing/creating/updating/deleting expenses, recurring expenses/invoices, bank transactions, customer payments, projects (and project users/tasks/comments), contacts (and contact persons/addresses), invoices (incl. email/templates/credits/payments), bills (incl. payments/comments), bank account rules, organizations, or chart-of-accounts entries; categorizing/matching bank transactions; issuing refunds on customer payments; uploading or downloading local receipts and attachments; sending invoices/reminders by email; applying credits or unapplying payments. Triggers on phrases like "create an expense in Zoho", "categorize this bank transaction", "find the contact named X", "refund this payment", "mark this project active", "send the invoice to the customer", "attach this receipt", "download the bill PDF", or any mention of a Zoho Books record ID combined with a CRUD or file operation. Prefer this CLI over the Zoho MCP when the user will consume IDs in JavaScript (MCP loses precision on 19-digit IDs) or when binary uploads/downloads are involved.
---

# Zoho Books CLI (`zb`) — agent usage

A thin command-line wrapper over the Zoho Books v3 REST API designed for agents:
- Outputs a single JSON object on stdout (`{"ok": true, "data": ...}`).
- Errors go to stderr with a stable `error.code` and a meaningful exit code.
- Preserves 19-digit Zoho IDs as strings end-to-end (the MCP loses precision in JS runtimes).
- Native multipart for local file uploads (the MCP can't carry binary).

This file is the **agent-user** reference. For contributing code to the CLI, see [`AGENTS.md`](https://github.com/madisonrickert/zoho-books-cli/blob/main/AGENTS.md). For human onboarding, see [`README.md`](https://github.com/madisonrickert/zoho-books-cli/blob/main/README.md).

Repo: <https://github.com/madisonrickert/zoho-books-cli>

## When to use this CLI vs. the Zoho MCP

| Task | Use |
| ---- | --- |
| Upload or download a local file (receipts, bill/invoice attachments, document PDFs) | **`zb`** |
| CRUD anywhere where the response IDs flow through a JS/Node runtime | **`zb`** (preserves 19-digit IDs as strings) |
| The two-step workflows below (apply payments to a bill, apply credits to an invoice, write off / cancel write-off, mark sent / void / draft) | **`zb`** has them as first-class verbs |
| MCP-only conveniences (full-text search, AI suggestions) | MCP |
| An endpoint neither wraps | `zb raw <METHOD> <path>` |

Both surfaces are valid; mix them freely. The IDs `zb` returns are safe to feed straight into MCP calls.

## Preconditions

```bash
zb --version       # confirms install
zb auth status     # → {"ok": true, "data": {"authenticated": true, ...}}
zb org current     # → {"ok": true, "data": {"org_id": "...", ...}}
```

If `auth status` shows `authenticated: false`, **stop** and tell the user to run `zb auth login --client-id <id> --client-secret <secret>`. You cannot complete the OAuth flow on their behalf.

If `org current` returns a null `org_id`, run `zb org list` and ask the user which organization to target, then `zb org use <id>`.

## IDs must be strings in `--body` JSON

Zoho Books IDs are 19 digits. JavaScript's `Number` type starts losing precision past ~16 digits (`2^53 − 1`). When you construct `--body` JSON, **quote IDs as strings**:

```bash
# Correct
zb expenses create --body '{"account_id":"9820000005670010000","amount":42.50}'

# Dangerous — a JS consumer of the response will silently corrupt the ID
zb expenses create --body '{"account_id":9820000005670010000,"amount":42.50}'
```

Numbers in JSON bodies (amounts, quantities, dates expressed as ints) are fine; the rule is specifically about ID-shaped fields.

## Thin-wrapper convention

Every wrapped command takes one or both of:

- `--query key=value` (repeatable) and / or `--params '<JSON>'` (single JSON object) for URL query params. Both merge into the final query dict; `--params` wins on conflict.
- `--body '<json>'` or `--body @path/to/file.json` for the request body. IDs in the body must be strings.

`--page` and `--per-page` are first-class on every list. Opt-in `--page-all` (with `--page-limit` and `--page-delay`) auto-paginates and emits **NDJSON** — one JSON line per page.

There are no typed per-field flags. Build the JSON body from Zoho's API docs.

## Output contract (parse this, not stdout text)

**Success** → stdout, exit 0:

```json
{"ok": true, "data": {...}}
```

**Error** → stderr, non-zero exit:

```json
{"ok": false, "error": {"code": "<code>", "message": "<human>", "details": {...}}}
```

Stable `error.code` + exit codes:

| `error.code` | Exit | Agent response |
| ------------ | ---- | -------------- |
| `auth_required` | 2 | Tell user to run `zb auth login`. Do not retry. |
| `auth_expired`  | 2 | Refresh token rejected; user must re-login. |
| `auth_failed`   | 2 | Login/refresh exchange failed; check client_id/secret. |
| `validation`    | 3 | Bad inputs (missing file, unsupported type, file >10 MB, malformed JSON body). Fix and retry. |
| `not_found`     | 4 | The record ID doesn't exist. Surface clearly; offer to list/search. |
| `api_error`     | 4 | Zoho returned 4xx. `details.zoho_code` carries Zoho's specific error code. |
| `rate_limited`  | 5 | `details.retry_after_s` says how long to wait. |
| `network`       | 6 | Transient. Retry once; if persistent, surface to user. |
| `unknown`       | 1 | Surface the message verbatim. |

## Output formatting flags

| Flag | Effect |
| ---- | ------ |
| `--format json` (default) | One-line JSON object. |
| `--format yaml` | YAML. |
| `--format table` | Rich table (humans). |
| `--format csv` | CSV (list responses only — falls back to JSON otherwise). |
| `--dry-run` | Print the request that *would* be sent (method, url, query, body, headers, files) as the success payload. **No network I/O, no token refresh.** Use to preview destructive calls. |

## Command tree (agent-relevant verbs)

> Authoritative tree: `zb --list-commands` returns the full command list as JSON.

### Auth & organization

```bash
zb auth login|status|refresh|logout
zb org list|use|current      # local config (target org)
zb org get <organization_id>     # API: GET /organizations/{id}
zb org update <organization_id> --body '{...}'
```

### Expenses (full surface + binary)

```bash
zb expenses list|get|create|update|update-by-custom-field|delete
zb expenses receipt upload|get|delete   # single receipt per expense; replaces existing
zb expenses attachments add|delete      # multiple supplementary files
zb expenses comments list
```

### Recurring expenses

```bash
zb recurring-expenses list|get|create|update|update-by-custom-field|delete
zb recurring-expenses stop|resume
zb recurring-expenses children          # child expenses
zb recurring-expenses history           # comments / activity
```

### Bank transactions + rules + statements

```bash
zb bank-transactions list|get|create|update|delete
zb bank-transactions match|matches|unmatch|exclude|restore|uncategorize
zb bank-transactions categorize generic|expense|vendor-payment|customer-payment|payment-refund|vendor-payment-refund|credit-note-refund|vendor-credit-refund
zb bank-transactions statements import|last-imported|delete

zb bank-rules list|get|create|update|delete   # /bankaccounts/rules; list requires account_id query param
```

### Bills (full)

```bash
zb bills list|get|create|update|update-by-custom-field|delete
zb bills mark-void|mark-open
zb bills email                          # POST /bills/{id}/email
zb bills payments list|apply|delete     # `delete` unapplies a payment row
zb bills comments list
zb bills attachments add|get|delete     # `get` writes the file to --output
```

### Invoices (full)

```bash
zb invoices list|get|create|update|update-by-custom-field|delete
zb invoices mark-sent|mark-void|mark-draft
zb invoices write-off|cancel-write-off
zb invoices email                       # ad-hoc email
zb invoices reminders send              # uses Zoho's payment-reminder template (placeholders, dunning rules)
zb invoices payments list               # read-only; record payments via `customer-payments create`
zb invoices credits list|apply|delete   # apply existing credit-notes / customer-payments
zb invoices comments list|add|delete
zb invoices documents get|download|delete   # `download` writes bytes via responseformat=pdf|html
zb invoices attachments add|get|delete
zb invoices templates list|apply
```

### Recurring invoices

```bash
zb recurring-invoices list|get|create|update|update-by-custom-field|delete
zb recurring-invoices stop|resume
zb recurring-invoices history
zb recurring-invoices templates apply <id> <template_id>
```

### Customer payments

```bash
zb customer-payments list|get|create|update|update-by-custom-field|delete
zb customer-payments refunds list|get|create|update|delete
```

### Projects (full)

```bash
zb projects list|get|create|update|update-by-custom-field|delete
zb projects mark-active|mark-inactive|clone
zb projects invoices                    # invoices billed against this project
zb projects users list|get|add|invite|update|delete
zb projects tasks list|get|add|update|delete
zb projects comments list|add|delete
```

### Contacts (full)

```bash
zb contacts list|search|get|create|update|update-by-custom-field|delete
zb contacts mark-active|mark-inactive
zb contacts comments
zb contacts addresses list|add|update|delete <contact_id> [<address_id>] ...
zb contacts persons list|get|create|update|delete|mark-primary
```

### Chart of accounts

```bash
zb chart-of-accounts list|get|create|update|delete
zb chart-of-accounts mark-active|mark-inactive
zb chart-of-accounts transactions list|delete
```

### Escape hatch

```bash
zb raw <GET|POST|PUT|DELETE> <path> [--query k=v] [--body '<json>'|@file.json] [--file field=path]
```

### File constraints (validated client-side)

- Types: `.pdf`, `.jpg`, `.jpeg`, `.png`, `.gif`
- Size: ≤ 10 MB per file

## Multi-file upload semantics

`attachments add <id> file1 file2 ...` does **not** abort on the first failure. Iterate `data.results[]`:

```json
{
  "ok": true,
  "data": {
    "expense_id": "...",
    "results": [
      {"file": "a.pdf", "ok": true,  "response": {...}},
      {"file": "b.exe", "ok": false, "error": {"code": "validation", ...}}
    ]
  }
}
```

`receipt upload` (one file per expense) returns success/failure as the top-level envelope and **replaces** any existing receipt.

## Idempotency notes

- `receipt upload` replaces.
- `attachments add` appends — calling twice with the same file creates two attachments.
- `attachments delete` and `receipt delete` are idempotent; deleting an already-deleted item returns `not_found`.
- Status verbs (`mark-active`, `mark-inactive`, `mark-sent`, `mark-void`, `stop`, `resume`, etc.) are server-validated for eligibility — you can call them on a record already in the target state without harm, but the response message will reflect Zoho's view.
- `bills payments delete` and `invoices credits delete` only **unapply** an application row; the underlying payment / credit-note record is untouched and re-applicable elsewhere.

## Typical agent flows

**Attach a receipt to an expense:**
1. `zb auth status` (verify) → `zb org current` (verify org_id).
2. `zb expenses receipt upload <expense_id> /path/to/file.pdf`.
3. Parse response: on `ok:true`, confirm `data.uploaded` (filename) and `data.size_bytes`. On `error.code=not_found`, offer to list recent expenses to find the right ID.

**Email an invoice:**
1. `zb invoices email <invoice_id>` — empty body sends Zoho's default to the saved-on-record recipients.
2. To override recipients/subject: `--body '{"to_mail_ids":["a@b.com"],"subject":"...","body":"<p>…</p>"}'`.
3. To attach the PDF: `--query send_attachment=true`.
4. For dunning / overdue reminders that pick up the org's payment-reminder template, use `zb invoices reminders send` instead.

**Apply credits to an invoice:**
1. Discover applicable credits via `zb customer-payments list` and `zb raw GET /creditnotes`.
2. `zb invoices credits apply <invoice_id> --body '{"apply_creditnotes":[{"creditnote_id":"...","amount_applied":100}]}'`.
3. Inspect the result via `zb invoices credits list <invoice_id>`.

**Categorize an uncategorized bank transaction as an expense:**
1. `zb bank-transactions list --query status=uncategorized` (or `--query account_id=...`).
2. `zb bank-transactions categorize expense <txn_id> --body '{"account_id":"...","amount":...,"date":"..."}'`.
3. Confirm via `zb bank-transactions get <txn_id>`.

## Discoverability

```bash
zb --list-commands         # full tree as JSON
zb <group> --help          # per-group help
zb <group> <cmd> --help    # per-command help (shows --body / --query expectations)
```

Use `--list-commands` after a CLI upgrade to discover new verbs without re-reading this skill.

## Full developer / contributor reference

See [`AGENTS.md`](https://github.com/madisonrickert/zoho-books-cli/blob/main/AGENTS.md) for architecture, contribution patterns, and the test contract (relevant only if you're modifying the CLI itself).
