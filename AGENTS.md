# AGENTS.md — agent-developer guide

For agents (and humans) **contributing code**. Agent-**user** contract is in [`skills/zoho-books/SKILL.md`](skills/zoho-books/SKILL.md); human onboarding is in [`README.md`](README.md).

## Layout

- `cli.py` — root Typer app, sub-app registration, error glue.
- `client.py` — HTTPX wrapper: region routing, `organization_id` injection, 401-refresh-retry, 429 backoff (max 3), `--dry-run` short-circuit.
- `auth.py` / `storage.py` / `config.py` — OAuth + keyring/file token persistence.
- `regions.py`, `output.py`, `errors.py`, `_uploads.py` — region URLs, JSON/YAML/table/CSV emission, typed exceptions + exit codes, multipart validation.
- `commands/<module>.py` — one module per Zoho v3 resource. Sub-collections are nested `typer.Typer()` sub-apps registered on the parent's `app`.
- `commands/_shared.py` — helpers used by every wrapped module. Don't reinvent.
- `tests/test_<module>.py` — one per command module; `conftest.py` has the `in_memory_storage` and `fake_cfg` fixtures.

## Thin-wrapper rule

Each wrapped command is a 1:1 map onto a Zoho v3 endpoint, accepting:

- `--body '<json>'` or `--body @file.json` — parsed via `_shared.parse_body`.
- `--query k=v` (repeatable) and/or `--params '<JSON>'` — merged via `_shared.parse_query_pairs` (`--params` wins).
- `--page` / `--per-page` / `--page-all` / `--page-limit` / `--page-delay` on every list.

**No typed per-field flags** — JSON body keeps the surface stable as Zoho evolves. **Composed commands** (one CLI call, multiple API ops) **must** be prefixed with `+` (e.g. `zb expenses +from-receipt`); bare names always mean a single-endpoint wrapper.

## Response emission

Route every response through one of these — don't invent new shapes.

- `emit_list_paginated(client, path, query, key, ...)` — list endpoints; handles `--page-all` NDJSON.
- `emit_list(resp, key)` — flat sub-resources without `page_context`.
- `emit_object(resp)` — single-record GET/PUT/POST. Strips Zoho's `code`/`message`.
- `emit_action(id_field, id_value, resp)` — verbs without a body (`delete`, `mark-active`, `stop`, ...).

## Envelope keys: live-verify, don't guess

When wrapping a new surface, **call the endpoint live** against a real Zoho org and confirm the collection / object key (`bills` vs `bill_list`, `task` vs `tasks` — the singular `task` is real). A wrong guess silently returns empty `items[]`. Record verified keys in the module docstring.

## IDs as strings

Zoho IDs are 19 digits, exceeding JS's `Number.MAX_SAFE_INTEGER`. The CLI never coerces them; Python ints are arbitrary precision so `--body` round-trips safely. **Every `create` / `update` needs a regression test** that sends a 19-digit JSON-number literal and asserts wire-level preservation.

## Tests (respx + `CliRunner`)

Mirror `tests/test_contacts.py`. Per command:

- Happy-path test asserting response shape and (for writes) wire body.
- 19-digit-ID preservation test on every `create` / `update`.
- Header test on every `update-by-custom-field` (`X-Unique-Identifier-Key`/`-Value`, `X-Upsert`).
- Binary downloads: success + 404 (asserts no partial file or parent dir).
- Action verbs: path hit + `data.<id_field>` round-trip.

`uv run pytest` stays green at every commit.

## Lint / format

```bash
uv run ruff check src tests
uv run ruff format --check src tests
```

Pre-commit runs both; don't `--no-verify`.

## Public contract stability

The JSON shapes in [`SKILL.md`](skills/zoho-books/SKILL.md) are public. Adding fields to `data` is fine; renaming/removing keys is breaking and needs a major bump.

## Security

- **Never log tokens.** Stored in OS keyring (preferred) or `~/.config/zoho-books-cli/credentials.json` at `0600`. Mask before any debug print.
- **Never commit secrets.** `.env`, `credentials.json`, `.zb_*` are gitignored; `detect-secrets` runs in pre-commit.
- **Validate uploads.** `_uploads.validate` enforces type + size. Don't bypass.
- **No destructive Zoho calls in tests** — all HTTP is respx-mocked. Live integration tests must be env-gated.
- **`zb raw` is intentionally unfiltered** — don't add path/method validation.

Disclosure policy: [`SECURITY.md`](SECURITY.md).

## Workflow

Live published package. Substantive changes go through review before landing on `main`:

- One feature per branch (`feat/<surface>`). Atomic commits within: module → `cli.py` registration → tests → review fixes. Combine work touching the same file in one branch.
- Run the `superpowers:code-reviewer` agent before merging. Address every Should-fix; document each Nit.
- Trivial changes (typo fixes, dep bumps, lint) land on `main` directly. Boundary: `~/.claude/projects/.../memory/feedback_pr_ceremony.md`.

## Pre-merge checklist

1. `uv run pytest` green.
2. `uv run ruff check src tests` + `ruff format --check` clean.
3. New commands appear in `zb --list-commands`.
4. ≥1 `--dry-run` smoke per new command — confirms method/url/body shape.
5. Live read against a real org for any new GET — confirms envelope keys.
6. Reviewer pass with fixes applied.
7. README / SKILL / AGENTS updated if the public surface changed; `__version__` and `pyproject.toml` bumped together for a release.

## When in doubt

1. Read 2-3 similar existing modules in `commands/`.
2. Read `_shared.py`.
3. Read the corresponding `tests/test_<module>.py` — the executable spec.

If those don't answer it, ask before inventing a new pattern.
