# zoho-books-cli

An agent-first command-line interface for [Zoho Books](https://www.zoho.com/books/). Built to fill feature gaps in the [Zoho Books MCP server](https://www.zoho.com/books/api/) — most notably, **uploading local receipt files and attachments to expenses, bills, and invoices**, which MCP's JSON-RPC interface cannot do cleanly.

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

### Escape hatch — any endpoint

```bash
zb raw GET /expenses --query "status=unfiled"
zb raw POST /contacts --body '{"contact_name":"Acme"}'
```

## Command tree

```
zb --list-commands         # machine-readable command tree (JSON)

zb auth login|status|refresh|logout
zb org list|use|current
zb expenses receipt upload|delete
zb expenses attachments add|delete
zb bills attachments add|delete
zb invoices attachments add|delete
zb raw <METHOD> <path>
```

## Output contract

All commands print a single JSON object:

- **Success** → stdout: `{"ok": true, "data": {...}}`
- **Error** → stderr: `{"ok": false, "error": {"code": "...", "message": "...", "details": {...}}}`

Pass `--pretty` for human-readable output.

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

## Out of scope for v1

Listing/getting expenses, invoices, contacts, customer payments, bank transactions, etc. — all already well-supported by the [Zoho Books MCP](https://www.zoho.com/books/api/). This CLI concentrates on the gap MCP can't fill. Use `zb raw` for anything not wrapped.

## Security

Never commit secrets. See [`SECURITY.md`](SECURITY.md) for disclosure policy and [`.env.example`](.env.example) for configuration.

## License

MIT — see [`LICENSE`](LICENSE).
