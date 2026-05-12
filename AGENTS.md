# AGENTS.md — agent-developer guide

For agents (and humans) **contributing code**. Agent-**user** contract is in [`skills/zoho-books/SKILL.md`](skills/zoho-books/SKILL.md); human onboarding is in [`README.md`](README.md); upgrade story for existing users is in [`MIGRATION.md`](MIGRATION.md).

## Layout

- `src/main.rs` — entry point: parses CLI, dispatches, maps errors to exit codes, installs the panic hook.
- `src/cli.rs` — clap root, global options (`--format`, `--pretty`, `--dry-run`, `--version`, `--list-commands`), sub-app registration, the `Ctx` struct passed to every command, the `--list-commands` manifest walker.
- `src/client.rs` — `reqwest::blocking` wrapper: region routing, `organization_id` injection, 401-refresh-retry, 429 backoff (max 3), `--dry-run` short-circuit, multipart upload path.
- `src/auth.rs` / `src/storage.rs` / `src/config.rs` — OAuth (loopback port 8976, `tiny_http`) + keyring/file token persistence + `RuntimeConfig` precedence resolution.
- `src/regions.rs`, `src/output.rs`, `src/errors.rs`, `src/uploads.rs` — region URLs, JSON/YAML/table/CSV emission, typed errors + exit codes, multipart validation.
- `src/shared.rs` — `parse_body` (returns `Box<RawValue>` for 19-digit-ID preservation), `parse_query_pairs`, `emit_list`, `emit_object`, `emit_action`, `emit_list_paginated` (NDJSON streaming).
- `src/commands/common.rs` — `ListArgs`, `BodyArgs`, `CustomFieldUpdateArgs`, plus the request-building + emit shortcuts (`list`, `create`, `get`, `update`, `update_custom`, `delete`, `action`, `action_with_body`). Used by every domain module.
- `src/commands/<module>.rs` — one module per Zoho v3 resource. Nested sub-apps are clap `Subcommand` enums under the module's `Sub` enum.

## Thin-wrapper rule

Each wrapped command is a 1:1 map onto a Zoho v3 endpoint, accepting:

- `--body '<json>'` or `--body @file.json` — parsed via `shared::parse_body`, which returns a `Box<RawValue>` so the original bytes pass through to the wire without numeric round-tripping.
- `--query k=v` (repeatable) and/or `--params '<JSON>'` — merged via `shared::parse_query_pairs` (`--params` wins).
- `--page` / `--per-page` / `--page-all` / `--page-limit` / `--page-delay` on every list, exposed through the shared `ListArgs` struct.

**No typed per-field flags** — JSON body keeps the surface stable as Zoho evolves. **Composed commands** (one CLI call, multiple API ops) **must** be prefixed with `+` (e.g. `zb expenses +from-receipt`); bare names always mean a single-endpoint wrapper.

## Response emission

Route every response through one of these — don't invent new shapes.

- `common::list(ctx, path, args, key)` — list endpoints; uses `shared::emit_list_paginated` for `--page-all` NDJSON streaming.
- `common::emit_list_flat(resp, key, ctx)` — flat sub-resources without `page_context`.
- `common::emit_object(resp, ctx)` — single-record GET/PUT/POST. Strips Zoho's `code`/`message`.
- `common::emit_action(id_field, id_value, resp, ctx)` — verbs without a body (`delete`, `mark-active`, `stop`, ...).
- `common::emit_success_raw(data, ctx)` — for composed commands that build their own envelope (attachments batch, downloads, etc.).

## Envelope keys: live-verify, don't guess

When wrapping a new surface, **call the endpoint live** against a real Zoho org and confirm the collection / object key (`bills` vs `bill_list`, `task` vs `tasks` — the singular `task` is real). A wrong guess silently returns empty `items[]`. Record verified keys in the module docstring.

## IDs as strings

Zoho IDs are 19 digits, exceeding JS's `Number.MAX_SAFE_INTEGER`. The CLI never coerces them. In Rust, `--body` is parsed into a `serde_json::value::RawValue` so the original bytes are passed through to the wire unchanged. Composed commands that must mutate the body before sending use `serde_json` with the `arbitrary_precision` feature and only read string/raw fields. **Every `create` / `update` path is covered by the wire-level 19-digit-ID test in `client::tests::nineteen_digit_id_in_post_body_preserved_on_wire`**; new commands inherit that guarantee by going through `client::Client::post`/`put` rather than building requests by hand.

## Tests (`mockito` + `assert_cmd` + inline `#[cfg(test)]`)

Pattern per command module:

- Inline `#[cfg(test)] mod tests` for plumbing-level checks. Use `MemoryStorage` (gated `#[cfg(test)]`) for fixtures.
- `mockito::Server::new()` for HTTP mocking. `Client::with_api_override(server.url())` (also `#[cfg(test)]`) replaces the production API base URL.
- Happy-path test asserting response shape and (for writes) wire body via `match_body`.
- Header test on every `update-by-custom-field` (`X-Unique-Identifier-Key`/`-Value`, `X-Upsert`) — `client::tests::custom_headers_forwarded_to_request` covers the generic path.
- Binary downloads: success + 404 (asserts no partial file or parent dir).
- Action verbs: path hit + `data.<id_field>` round-trip.

`cargo test` stays green at every commit.

## Lint / format

```bash
cargo clippy --all-targets -- -D warnings
cargo fmt --check
```

Both must be clean before merge. `#[allow(...)]` suppressions are allowed during in-flight stubbing but **must be removed before declaring a feature done** — the diff that adds an `#[allow]` must also note when the suppression will be lifted.

## Public contract stability

The JSON shapes in [`SKILL.md`](skills/zoho-books/SKILL.md) are public. Adding fields to `data` is fine; renaming/removing keys is breaking and needs a major bump.

The 17 invariants enumerated in the original port plan ([`bench/cli-latency/RESULTS.md`](bench/cli-latency/RESULTS.md) summarises the perf side; the architectural contract lives in commit history and the `superpowers:writing-plans` artifact) define what "drop-in" means. Don't break:

1. Envelope shapes (`{ok: true, data: ...}` / `{ok: false, error: {code, message, details}}`).
2. Exit codes (0/1/2/3/4/5/6).
3. NDJSON streaming under `--page-all`: one JSON object per line, `\n`-terminated, flushed after each page.
4. Credentials JSON schema (7 fields, optional, 0600).
5. Keyring slot: service `zoho-books-cli`, account `credentials`.
6. Region URL map.
7. Loopback port 8976.
8. `organization_id` auto-injection on every request that's not `skip_org_id`.
9. 401 → silent refresh → retry-once. 429 → up to 3 retries, exponential backoff, honor `Retry-After`.
10. Multipart validation (pdf/jpg/jpeg/png/gif; 10 MB cap).
11. 19-digit-ID preservation via `RawValue` pass-through.
12. `--dry-run` short-circuits before any HTTP send and scrubs `Authorization`. Composed commands (one CLI call, multiple internal client calls) must exit at the FIRST internal call — see "DryRunOk propagation" below.
13. Token refresh side effect: writes new access_token + expires_at to storage.
14. Stdout/stderr discipline: success → stdout once; error → stderr once.
15. Config precedence: CLI flag > env > stored > default.
16. Missing `org_id` → `validation` (exit 3), not `auth_required` (exit 2).
17. Batch attachment `add` tolerates partial failure (per-file `Result` in the result array, no `?`-propagation).

## DryRunOk propagation

`Client::request` signals dry-run completion by emitting the preview envelope on stdout and returning `Err(ZohoError { kind: ErrorKind::DryRunOk, .. })`. The dispatch layer in `main` treats this kind as success (exit 0) and suppresses the error envelope.

The wrinkle is composed commands: anything that calls the client inside a loop with per-iteration error catching (see `expenses::attachments_add`, `bills::attachments_add`, `invoices::attachments_add`). Those loops must **propagate `DryRunOk` immediately**, before the per-iteration error handler runs — otherwise the preview is emitted N times and a fake "results" envelope follows. Invariants 12 ("exit at first call") and 14 ("stdout once") both break.

The pattern is one match arm:

```rust
match upload_one(...) {
    Ok(resp) => { /* store result */ }
    Err(e) if crate::errors::ErrorKind::DryRunOk == e.kind => return Err(e),
    Err(e) => { /* store fake-failure result */ }
}
```

No helper function (3 sites today; would be premature abstraction). Document the rule here; spot it in code review when a new composed command lands.

## Security

- **Never log tokens.** Stored in OS keyring (preferred) or `~/.config/zoho-books-cli/credentials.json` at `0600`. Mask before any debug print.
- **Never commit secrets.** `.env`, `credentials.json`, `.zb_*` are gitignored; `detect-secrets` runs in pre-commit.
- **Validate uploads.** `uploads::validate` enforces type + size. Don't bypass.
- **No destructive Zoho calls in tests** — all HTTP is mockito-mocked. Live integration tests must be env-gated.
- **`zb raw` is intentionally unfiltered** — don't add path/method validation.

Disclosure policy: [`SECURITY.md`](SECURITY.md).

## Workflow

Live published package. Substantive changes go through review before landing on `main`:

- One feature per branch (`feat/<surface>`). Atomic commits within: module → `cli.rs` registration → tests → review fixes. Combine work touching the same file in one branch.
- Run the `superpowers:code-reviewer` agent before merging. Address every Should-fix; document each Nit.
- Trivial changes (typo fixes, dep bumps, lint) land on `main` directly. Boundary: `~/.claude/projects/.../memory/feedback_pr_ceremony.md`.

## Pre-merge checklist

1. `cargo test` green.
2. `cargo clippy --all-targets -- -D warnings` clean.
3. `cargo fmt --check` clean.
4. No `#[allow(...)]` suppressions remain that were added for stubbing.
5. New commands appear in `zb --list-commands`.
6. ≥1 `--dry-run` smoke per new command — confirms method/url/body shape.
7. Live read against a real org for any new GET — confirms envelope keys.
8. Reviewer pass with fixes applied.
9. README / SKILL / AGENTS / MIGRATION updated if the public surface changed; `Cargo.toml` version bumped for a release.

## Releases

`cargo-dist` powers the release pipeline. Tag-driven: push a `vX.Y.Z` tag, GitHub Actions cross-compiles binaries for macOS arm64/x86_64 and Linux x86_64, uploads them to a GitHub Release, and updates the Homebrew tap formula at `madisonrickert/homebrew-tap`. Configuration lives in `Cargo.toml` (`[workspace.metadata.dist]`) and `.github/workflows/release.yml`.

## When in doubt

1. Read 2-3 similar existing modules in `src/commands/`.
2. Read `src/commands/common.rs` for the shared helpers.
3. Read `src/client.rs` for the HTTP layer's invariants.
4. Read the corresponding inline `#[cfg(test)] mod tests` — the executable spec.

If those don't answer it, ask before inventing a new pattern.
