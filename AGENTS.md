# AGENTS.md — agent-developer guide

This file is for AI agents (and humans) **contributing code** to the `zoho-books-cli` repo. It captures the architectural conventions, quality expectations, and workflow rules a contributor needs to ship a change without breaking the agent-facing contract.

If you are an agent that **uses** the CLI to do work in Zoho Books — see [`skills/zoho-books/SKILL.md`](skills/zoho-books/SKILL.md). Don't conflate the two: SKILL is the agent-user contract; this file is the agent-developer contract.

For human onboarding (install, auth, headline examples), see [`README.md`](README.md).

## Architectural conventions

### One module per Zoho v3 surface

Each top-level Zoho resource gets its own file in `src/zoho_books_cli/commands/`:

- `expenses.py`, `recurring_expenses.py` — expense-side
- `invoices.py`, `recurring_invoices.py`, `bills.py` — sales / purchase docs
- `customer_payments.py`, `bank_transactions.py`, `bank_account_rules.py` — money movement
- `contacts.py`, `projects.py`, `chart_of_accounts.py` — master data
- `org.py` — local-config + API-level org management
- `auth.py`, `raw.py` — utility commands

Sub-collections (e.g. `users` / `tasks` / `comments` under projects) are nested `typer.Typer()` sub-apps registered on the parent module's `app`.

### Thin-wrapper rule

A wrapped command is a one-to-one map onto a Zoho v3 endpoint. It accepts:

- `--body '<json>'` or `--body @file.json` for the request body (parsed via `_shared.parse_body`).
- `--query key=value` (repeatable) and / or `--params '<JSON>'` for the query (merged via `_shared.parse_query_pairs`).
- First-class `--page`, `--per-page`, `--page-all`, `--page-limit`, `--page-delay` on every list command.

There are **no typed per-field flags**. The body is JSON the agent constructs from Zoho's API docs. This is intentional — it keeps the CLI surface stable as Zoho evolves their schema and avoids reimplementing every field as a flag.

A composed command (a single CLI call that performs multiple API operations) **must** be prefixed with `+` (e.g. `zb expenses +from-receipt`). Bare command names always mean a single-endpoint thin wrapper. Agents reading the command tree depend on this signal.

### Shared helpers (`commands/_shared.py`)

Every wrapped command should route response emission through one of:

- `emit_list_paginated(client, path, query, collection_key, ...)` — list endpoints. Handles `--page-all` NDJSON streaming and the standard `{items, page_context}` envelope shape.
- `emit_list(resp, collection_key)` — sub-resources Zoho returns without `page_context` (e.g. `/projects/{id}/users`). No `--page-all` plumbing.
- `emit_object(resp)` — single-record GET / PUT / POST. Strips Zoho's envelope `code`/`message` fields and emits the rest verbatim.
- `emit_action(id_field, id_value, resp)` — verbs with no meaningful body (delete, mark-active, stop, etc.). Emits `{<id_field>, "acted": true, "response": resp}`.

Do not invent new emission shapes. If a new shape is genuinely needed, add it to `_shared.py` so every module can use it.

### Envelope keys are live-verified, not guessed

When wrapping a new surface, **call the endpoint live** against a real Zoho org and confirm the response collection / object key (e.g. `bills` vs `bill_list`, `task` vs `tasks`). The thin-wrapper helpers depend on the right key; a wrong guess silently emits empty `items` arrays — the worst possible failure mode for agents.

The module docstring should record the verified keys near the top:

```python
"""...

Live-verified envelope keys against the user's Zoho org:
- /bills                  → bills / bill
- /bills/{id}/payments    → payments
- /bills/{id}/comments    → comments
"""
```

### IDs as strings, end-to-end

Zoho IDs are 19 digits and exceed JavaScript's `Number.MAX_SAFE_INTEGER`. The CLI never coerces ID-shaped fields to ints. Python ints in `--body` JSON round-trip safely (Python ints are arbitrary precision); the danger is downstream JS consumers, so the **agent-user contract** demands quoting IDs as strings in body JSON. The CLI enforces nothing here — but every `create` and `update` command should have a regression test that sends a 19-digit ID literal as a JSON number and asserts the wire body preserves it bit-for-bit.

### Client behavior

`src/zoho_books_cli/client.py` (`ZohoBooksClient`) handles:

- Region → base URL routing (`regions.py`).
- Automatic injection of `organization_id` as a query param.
- 401 → transparent refresh → retry-once.
- 429 → honor `Retry-After`, exponential backoff, max 3 retries.
- Typed exceptions (`auth.py`, `errors.py`) mapped to CLI exit codes via `cli.py:main()`.
- `--dry-run` short-circuit: emits the would-be request as the success payload and exits before any network I/O.

Don't bypass the client unless the endpoint genuinely cannot tolerate `organization_id` injection — and even then, prefer extending the client over inlining `httpx.get(...)` (the `org list` workaround in `commands/org.py:list_orgs` is a historical exception, not a precedent).

### Sub-app registration

Sub-app names should be human-readable, dash-separated:

```python
# in commands/<module>.py
attachments_app = typer.Typer(...)
app.add_typer(attachments_app, name="attachments")
```

Top-level groups go in `cli.py` alphabetically near related groups. Don't introduce a new group without a clear naming rationale (e.g., `bank-rules` is top-level rather than nested under `bank-transactions` because it's an administrative concern, not a transaction action).

## Quality expectations

### Tests

Every wrapped command needs respx + `CliRunner` coverage:

- Happy-path test for each verb, asserting both response shape and (for write verbs) the wire body.
- ID-as-string preservation test for every `create` / `update` (send a 19-digit literal as a JSON number, assert it survives the body parse and the request content).
- Header-contract test for every `update-by-custom-field` (asserts `X-Unique-Identifier-Key`, `X-Unique-Identifier-Value`, and `X-Upsert` are set / absent correctly).
- For binary downloads: success path + 404 path that asserts no partial file or parent directory was created.
- For action verbs returning `code/message` envelopes: assert the path was hit and `data.<id_field>` round-trips.

The test pattern is established in `tests/test_contacts.py`; mirror it. Don't introduce new test infrastructure unless the helper hits a real expressiveness limit.

`uv run pytest` must stay green at every commit.

### Lint / format

Ruff is the source of truth.

```bash
uv run ruff check src tests
uv run ruff format --check src tests
```

Both must pass. Pre-commit (`.pre-commit-config.yaml`) runs them on every commit; don't bypass with `--no-verify`.

### Output contract is stable

The JSON shapes documented in [`SKILL.md`](skills/zoho-books/SKILL.md) are part of the public contract. **Don't change them lightly** — agents pin against them. New fields in `data` are fine; renaming or removing existing keys is a breaking change that needs a major-version bump.

## Security expectations

- **Never log access tokens or refresh tokens.** They live in OS keyring (preferred) or `~/.config/zoho-books-cli/credentials.json` at `0600` (fallback). The auth code in `auth.py` and `storage.py` already handles this — don't print tokens for debugging without temporarily masking them.
- **Never commit secrets.** `.env`, `credentials.json`, `.zb_*`, etc. are in `.gitignore`. `detect-secrets` runs in pre-commit (`.secrets.baseline`).
- **Treat user-supplied paths as untrusted.** `_uploads.validate` checks size and type; don't add a code path that bypasses it for "performance."
- **Don't make destructive Zoho calls in tests.** All HTTP calls in the suite are respx-mocked. If you need a live integration test, gate it behind an env-var opt-in and document it.
- **`zb raw` is by design unfiltered.** Don't add server-side validation for paths/methods — it would only delay the inevitable Zoho 4xx, which the user can already read in the structured error.

For disclosure policy, see [`SECURITY.md`](SECURITY.md).

## Branch / commit / review workflow

- **Live project, live users.** No unreviewed changes land on `main`. Even solo-internal work goes through a critical senior-engineer review gate before merge.
- One feature per branch (`feat/<surface>`); separate branches for unrelated work to keep diffs reviewable. When two changes both extend the same module file (e.g. `addresses` and `persons` on `contacts.py`), combine them in one branch to avoid merge friction — but keep each commit atomic.
- Atomic commits within a branch: module first, sub-app registration in `cli.py` next (single line, easy to revert), tests last. Then any review-feedback commits as separate commits on top.
- Use the `superpowers:code-reviewer` agent (or equivalent) before merging. Address every Should-fix; document the resolution of every Nit (apply or explicitly skip with reasoning).
- Trivial changes (typo fixes, README polish, dependency bumps, lint fixes) can land on `main` directly without a branch — see the user's stated preferences in `~/.claude/projects/.../memory/feedback_pr_ceremony.md`.

## Verification checklist before merging a branch

1. `uv run pytest` — green.
2. `uv run ruff check src tests` and `uv run ruff format --check src tests` — clean.
3. New commands listed in `zb --list-commands | jq '.data.commands[].name'` — confirm they appear.
4. At least one `--dry-run` smoke per branch: `uv run zb --dry-run <new-command> ...` — verify method/url/body shape match the documented Zoho endpoint.
5. Live read against the user's real org (read-only) for any new GET endpoint — confirms envelope keys.
6. Code review pass with applied fixes.
7. README / SKILL / AGENTS docs updated if the public surface changed.

## File map

| File | What it owns |
| ---- | ------------ |
| `src/zoho_books_cli/cli.py` | Root Typer app, sub-app registration, `--list-commands`, error contract glue. |
| `src/zoho_books_cli/client.py` | HTTPX wrapper; auth refresh; 429 handling; `--dry-run` short-circuit. |
| `src/zoho_books_cli/auth.py`, `storage.py`, `config.py` | OAuth refresh and keyring/file persistence. |
| `src/zoho_books_cli/regions.py` | Region → base URL mapping. |
| `src/zoho_books_cli/output.py` | JSON / YAML / table / CSV emission; `emit_success`, `emit_error`. |
| `src/zoho_books_cli/errors.py` | Typed exceptions + exit codes. |
| `src/zoho_books_cli/_uploads.py` | File-type and size validation for multipart uploads. |
| `src/zoho_books_cli/commands/_shared.py` | Helpers used by every wrapped module. |
| `src/zoho_books_cli/commands/<module>.py` | One module per Zoho resource. |
| `tests/conftest.py` | `in_memory_storage` and `fake_cfg` fixtures. |
| `tests/test_<module>.py` | One test file per command module. |
| `skills/zoho-books/SKILL.md` | Agent-user contract — keep in sync with shipped commands. |
| `README.md` | Human onboarding. |
| `pyproject.toml` | Package metadata, ruff config, pytest config. Bump `version` here on a release. |

## When in doubt

Read three things in order:

1. The two or three most-similar existing modules in `commands/` — pattern fidelity wins.
2. `commands/_shared.py` — every wrapped command should use these helpers.
3. The corresponding `tests/test_<module>.py` — that's the executable spec for the agent-user contract.

If those don't tell you what to do, ask before inventing a new pattern.
