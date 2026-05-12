# AGENTS.md — agent-developer guide

For agents (and humans) **contributing code**. Agent-**user** contract is in [`skills/zoho-books/SKILL.md`](skills/zoho-books/SKILL.md); human onboarding is in [`README.md`](README.md); upgrade story for existing users is in [`MIGRATION.md`](MIGRATION.md).

## Layout

Every `src/*.rs` has a `//!` doc-comment at the top describing its role — `head -10 src/*.rs` is the fastest orientation. The high-level shape:

- `main.rs` → `cli.rs` (clap root + global options + `Ctx` + dispatch) → `commands/<module>.rs` (one per Zoho v3 resource) → `client.rs` (HTTP plumbing).
- Credentials path: `auth.rs` (OAuth flow) + `storage.rs` (keyring/file) + `config.rs` (precedence merge).
- Cross-cutting: `errors.rs`, `output.rs`, `regions.rs`, `uploads.rs`, `shared.rs`.
- The kit at `commands/common.rs` (arg structs `ListArgs`/`BodyArgs`/`CustomFieldUpdateArgs` + request-building + emit shortcuts) is used by every domain module. Nested sub-apps are clap `Subcommand` enums under each module's `Sub` enum.

## Thin-wrapper rule

Each wrapped command is a 1:1 map onto a Zoho v3 endpoint, accepting:

- `--body '<json>'` or `--body @file.json` — parsed via `shared::parse_body`, which returns a `Box<RawValue>` so the original bytes pass through to the wire without numeric round-tripping.
- `--query k=v` (repeatable) and/or `--params '<JSON>'` — merged via `shared::parse_query_pairs` (`--params` wins).
- `--page` / `--per-page` / `--page-all` / `--page-limit` / `--page-delay` on every list, exposed through the shared `ListArgs` struct.

**No typed per-field flags** — JSON body keeps the surface stable as Zoho evolves.

## Response emission

Route every response through one of the helpers in `src/commands/common.rs` (`list`, `emit_list_flat`, `emit_object`, `emit_action`, `emit_success_raw`, ...) — each is documented in-source. Don't invent new envelope shapes; if the existing shapes don't fit, the new command is probably misshapen.

## Envelope keys: live-verify, don't guess

When wrapping a new surface, **call the endpoint live** against a real Zoho org and confirm the collection / object key (`bills` vs `bill_list`, `task` vs `tasks` — the singular `task` is real). A wrong guess silently returns empty `items[]`. Record verified keys in the module docstring.

## IDs as strings

Zoho IDs are 19 digits, exceeding JS's `Number.MAX_SAFE_INTEGER`. The CLI never coerces them. In Rust, `--body` is parsed into a `serde_json::value::RawValue` so the original bytes are passed through to the wire unchanged. Composed commands that must mutate the body before sending use `serde_json` with the `arbitrary_precision` feature and only read string/raw fields. **Every `create` / `update` path is covered by the wire-level 19-digit-ID test in `client::tests::nineteen_digit_id_in_post_body_preserved_on_wire`**; new commands inherit that guarantee by going through `client::Client::post`/`put` rather than building requests by hand.

**Constraint introduced by `arbitrary_precision`:** when the feature is on (it is — see `Cargo.toml`), `serde_json::Value::Number` is internally string-backed. `Number::as_i64()` / `as_u64()` / `as_f64()` and the corresponding `is_*` predicates may return `None` even for values that *would* fit in those types, because the internal representation is the source-text string, not a typed integer. **Production code must not use these accessors.** If you need a numeric value out of a response, parse it from `Number::to_string()` or use `Number::as_str()` (only available with `arbitrary_precision`). The codebase currently has zero `as_i64`/`as_u64`/`as_f64`/`is_i64`/`is_u64` call sites in `src/` (verified by `rg`); keep it that way.

## Tests

Inline `#[cfg(test)] mod tests` in each module. Mockito for HTTP; `MemoryStorage` (gated `#[cfg(test)]`) for credential fixtures. `Ctx::new_for_test(server_url)` and `Ctx::new_for_test_dry_run(server_url)` build a context wired to a mock server.

Coverage policy:

- Plumbing-level invariants live in `src/client.rs`, `src/shared.rs`, `src/storage.rs`, `src/output.rs` tests. These catch the 17 invariants — 19-digit-ID preservation, 401-refresh-retry, dry-run scrubbing, etc. Read these as the executable spec.
- Each domain module has one `list_targets_<base>` smoke that asserts the BASE path is hit. Catches path-drift; does NOT catch envelope-key drift (covered by the "live-verify, don't guess" rule).
- Composed-command + per-iteration-error-handler loops need a DryRunOk-propagation regression test — see `commands::expenses::tests::attachments_add_dry_run_propagates_short_circuit` as the canonical example.
- Binary-download tests (success + 404, no partial file written, parent dir not created on failure) are **not** yet implemented per-module. Add them with new download commands.

For test overrides, see `Client::with_api_override` (replaces the API base URL) and `Client::with_accounts_override` (replaces the OAuth refresh endpoint, needed when exercising 401-refresh against a single mock server). Both are `#[cfg(test)]`-gated.

`cargo test` stays green at every commit.

## Lint / format

```bash
cargo clippy --all-targets -- -D warnings
cargo fmt --check
```

Both must be clean before merge. `#[allow(...)]` suppressions are allowed during in-flight stubbing but **must be removed before declaring a feature done** — the diff that adds an `#[allow]` must also note when the suppression will be lifted.

## Public contract stability

The JSON shapes in [`SKILL.md`](skills/zoho-books/SKILL.md) are public. Adding fields to `data` is fine; renaming/removing keys is breaking and needs a major bump.

The 17 invariants below define what "drop-in" means. ([`bench/cli-latency/RESULTS.md`](bench/cli-latency/RESULTS.md) summarises the perf side of the Python-to-Rust port; the full architectural contract is preserved in commit messages on `port/rust`.) Don't break:

1. Envelope shapes (`{ok: true, data: ...}` / `{ok: false, error: {code, message, details}}`).
2. Exit codes (0/1/2/3/4/5/6).
3. NDJSON streaming under `--page-all`: one JSON object per line, `\n`-terminated, flushed after each page.
4. Credentials JSON schema (7 fields, optional, 0600).
5. Keyring slot: service `zoho-books-cli`, account `credentials`.
6. Region URL map.
7. Loopback port 8976.
8. `organization_id` auto-injection on every request that's not `skip_org_id`.
9. 401 → silent refresh → retry-once. 429 → up to 3 retries, exponential backoff, **numeric `Retry-After` honored** (HTTP-date form is not parsed and falls through to backoff — Zoho's docs don't specify either form; see `parse_retry_after` docstring in `client.rs`).
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
    Err(e) if matches!(e.kind, crate::errors::ErrorKind::DryRunOk) => return Err(e),
    Err(e) => { /* store fake-failure result */ }
}
```

No helper function (3 sites today; would be premature abstraction). Document the rule here; spot it in code review when a new composed command lands.

## Security

- **Never log tokens.** Stored in OS keyring (preferred) or `~/.config/zoho-books-cli/credentials.json` at `0600`. Mask before any debug print.
- **Never commit secrets.** `.env*`, `credentials.json`, `*.pem`, `*.key`, and `secrets/` are gitignored; `detect-secrets` runs in pre-commit.
- **Validate uploads.** `uploads::validate` enforces type + size. Don't bypass.
- **No destructive Zoho calls in tests** — all HTTP is mockito-mocked. Live integration tests must be env-gated.
- **`zb raw` is intentionally unfiltered** — don't add path/method validation.

Disclosure policy: [`SECURITY.md`](SECURITY.md).

## Workflow

Live published package. Substantive changes go through review before landing on `main`:

- One feature per branch (`feat/<surface>`). Atomic commits within: module → `cli.rs` registration → tests → review fixes. Combine work touching the same file in one branch.
- Run a code-reviewer pass before merging. Address every Should-fix; document each Nit.
- Trivial changes (typo fixes, dep bumps, lint) land on `main` directly.

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

Hand-rolled tag-driven pipeline in `.github/workflows/release.yml`:

1. **verify-version** — fails the run if the tag doesn't match `Cargo.toml`'s version (gate before the long cross-compile jobs).
2. **build** — matrix-builds the release binary for `aarch64-apple-darwin`, `x86_64-apple-darwin`, and `x86_64-unknown-linux-gnu`. Each archive bundles the binary + `README.md` + `LICENSE` plus a SHA-256.
3. **github-release** — gathers the artifacts and creates the GitHub Release, with notes pointing at `MIGRATION.md`.
4. **brew-tap** (opt-in, gated by repo variable `HOMEBREW_TAP_ENABLED == 'true'`) — computes the tarball SHAs, writes a `Formula/zoho-books-cli.rb` with `on_macos { on_arm / on_intel }` and `on_linux` blocks, and pushes it to `madisonrickert/homebrew-tap` using the `HOMEBREW_TAP_TOKEN` repo secret.

The brew-tap job stays gated so the rest of the pipeline works on day one before the tap repo + PAT secret are configured. Flip the variable once both exist.

There is no `[workspace.metadata.dist]` section; `cargo-dist` was considered but skipped to keep the workflow free of an external generator's version churn.

## When in doubt

1. Read 2-3 similar existing modules in `src/commands/`.
2. Read `src/commands/common.rs` for the shared helpers.
3. Read `src/client.rs` for the HTTP layer's invariants.
4. Read the relevant `#[cfg(test)] mod tests` blocks — wire-path smoke tests in each domain module, plus deeper plumbing tests in `src/shared.rs`, `src/client.rs`, and `src/storage.rs`.

If those don't answer it, ask before inventing a new pattern.
