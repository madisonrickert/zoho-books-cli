# Contributing

## Dev setup

Requires a Rust toolchain (1.88+). Install via [rustup](https://rustup.rs) if you don't have one:

```bash
brew install rustup
rustup-init -y --default-toolchain stable --profile minimal
```

Then clone and build:

```bash
git clone https://github.com/madisonrickert/zoho-books-cli
cd zoho-books-cli
cargo build
```

## Running tests & lint

```bash
cargo test
cargo clippy --all-targets -- -D warnings
cargo fmt --check
```

All three must pass before pushing. Pre-commit hooks (if installed) run the same set automatically.

## Adding a new command group

1. Create `src/commands/<group>.rs` with a `pub struct Cmd` that wraps a `pub enum Sub` (clap `Subcommand`-derived). Use `Args`-derived structs for per-leaf args, flattening `commands::common::{BodyArgs, ListArgs, CustomFieldUpdateArgs}` where applicable.
2. Register the module in `src/commands/mod.rs` and add a variant to `cli::Commands` in `src/cli.rs`. Wire its `run(cmd, &mut ctx)` into the dispatch.
3. Every command must:
   - Take a `Ctx` and call into `commands::common::*` helpers rather than building requests by hand.
   - Return `errors::Result<()>`. Raise typed errors from `errors::ZohoError::*`; never `eprintln!` errors or call `std::process::exit` from a command.
   - Verify the Zoho collection / object envelope keys live against a real org before merging.
4. Add inline `#[cfg(test)] mod tests` per module using `mockito` to mock HTTP. `Client::with_api_override(server.url())` swaps the API base URL.

See [`AGENTS.md`](AGENTS.md) for the full thin-wrapper rule, response-emission helpers, and the 17 public-contract invariants.

## Commit hygiene

- Never commit tokens, `.env`, or `credentials.json`. The pre-commit hook will block most cases, but double-check with `git diff --cached` before committing.
- Conventional-style prefixes (`feat:`, `fix:`, `docs:`, `refactor:`, `bench:`) are appreciated but not required.
