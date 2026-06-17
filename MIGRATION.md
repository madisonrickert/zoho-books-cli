# Migrating from Python 0.5.x to Rust 1.0.0

`zoho-books-cli` v1.0.0 is a full Rust rewrite. The binary name (`zb`), the
command tree, the JSON envelope shapes, the stored credentials, the OAuth
loopback port, the file-fallback path, and the keyring slot are all unchanged,
so for most users this is a one-line install swap with no re-authentication.

Per-call cold-start latency drops ~30× (117 ms → 4 ms) and memory footprint
drops ~5× (38 MB → 7.5 MB). See [`bench/cli-latency/RESULTS.md`](bench/cli-latency/RESULTS.md)
for the full benchmark table.

## Transition

```bash
# 1. Uninstall the Python version. Leaves credentials in place; they live in
#    the OS keyring and ~/.config/zoho-books-cli/credentials.json, both untouched
#    by uv tool uninstall.
uv tool uninstall zoho-books-cli

# 2. Install the Rust version.
brew install madisonrickert/tap/zoho-books-cli
# or, if you don't use brew:
cargo install --git https://github.com/madisonrickert/zoho-books-cli

# 3. Verify the new binary is on PATH and is the Rust one.
which zb         # should point to /opt/homebrew/bin/zb or ~/.cargo/bin/zb,
                 # NOT ~/.local/bin/zb
zb --version     # should print {"ok":true,"data":{"version":"1.0.0"}}

# 4. Verify existing credentials still work. This is the drop-in proof.
zb auth status   # should report "authenticated":true without prompting for re-auth
zb org list      # should succeed against your existing org
```

## What stays the same

- **Binary name.** Still `zb`.
- **Command tree.** Every subcommand from Python 0.5.x is present in Rust 1.0.0
  with the same arguments, flags, and positional layout. `zb --list-commands`
  emits the same JSON manifest agents use for discovery.
- **JSON envelopes.** Success → `{"ok": true, "data": {...}}` on stdout. Error
  → `{"ok": false, "error": {"code", "message", "details"}}` on stderr. Same
  codes, same exit codes (0/1/2/3/4/5/6 per the documented table).
- **Credentials.** Read from the same keyring slot (service `zoho-books-cli`,
  account `credentials`) and the same 0600 file at
  `~/.config/zoho-books-cli/credentials.json` (or the OS-equivalent under
  `dirs::config_dir()`). Same 7-field JSON schema.
- **OAuth.** Same loopback port (8976), same redirect URI
  (`http://localhost:8976/callback`), same scope (`ZohoBooks.fullaccess.all`),
  same `access_type=offline` + `prompt=consent` semantics.
- **Regions.** Same `us`/`eu`/`in`/`au`/`jp`/`ca`/`sa` codes mapping to the same
  accounts + API URL pairs.
- **Environment variables.** `ZOHO_REGION`, `ZOHO_ORG_ID`, `ZOHO_CLIENT_ID`,
  `ZOHO_CLIENT_SECRET`, `ZOHO_REFRESH_TOKEN` work identically.
- **Dry-run.** `zb --dry-run <any command>` emits the same
  `{method, url, query, headers, json_body, files}` preview.
- **Skill packaging.** `skills/zoho-books/SKILL.md` is untouched. If you have it
  symlinked into `~/.claude/skills/`, no action needed.

## What changes for power users

- **Install path.** Binary now ships as a single self-contained executable
  rather than a Python venv. ~3.3 MB on disk vs ~16 MB for the uv-tool tree.
- **Build dependency.** No longer needs Python on the user's machine. Building
  from source now needs a Rust toolchain (1.88+) instead of `uv` + Python 3.11+.
  Pre-built binaries via `brew install` or GitHub Releases require nothing.
- **Error trace on internal panics.** Rust's panic handler emits the
  `{"ok": false, "error": {"code": "unknown", ...}}` envelope rather than a
  multi-line backtrace, so the output contract holds even on unexpected
  failures. The `details.message` field includes the panic location for
  debugging.

## What `uv tool upgrade` does now

`uv tool upgrade zoho-books-cli` (or a fresh `uv tool install git+https://github.com/madisonrickert/zoho-books-cli` against the default branch) installs a **deprecation shim** (version 0.6.0, no dependencies, no real CLI). Running `zb` after that prints:

```json
{"ok":false,"error":{"code":"deprecated_install","message":"zoho-books-cli has moved from Python to a single Rust binary as of v1.0.0...","details":{"install_commands":{"homebrew":"brew install madisonrickert/tap/zoho-books-cli","cargo":"cargo install --git https://github.com/madisonrickert/zoho-books-cli","github_releases":"..."},...}}}
```

and exits 78 (`EX_CONFIG` from sysexits.h, distinct from the normal exit-code table). That's the signal to follow the transition steps above.

If you want the old Python 0.5.0 CLI to keep working unchanged for now, pin to that tag: `uv tool install 'git+https://github.com/madisonrickert/zoho-books-cli@v0.5.0'`. The 0.5.0 tag is preserved indefinitely and will keep installing the real Python implementation.

## Edge cases

### PATH order conflicts

If `~/.local/bin` (where `uv tool install` placed the Python `zb` shim) sits
ahead of `/opt/homebrew/bin` in your `$PATH`, step 1 must complete fully
before step 2, or `zb` will still resolve to the old Python binary.

```bash
which -a zb      # lists all candidates; the first one wins
echo $PATH | tr ':' '\n' | head -10
```

If the Python shim persists after `uv tool uninstall`, remove it manually:
`rm ~/.local/bin/zb`.

### Stale shell aliases

`uv tool uninstall` doesn't touch shell rc files. If you hand-installed an
alias like `alias zb='~/Developer/zoho-books-cli/.venv/bin/zb'` in `~/.zshrc`
or `~/.bashrc`, that alias will silently override the brew binary.

```bash
grep -E "alias\s+zb=" ~/.zshrc ~/.bashrc ~/.profile 2>/dev/null
```

Remove any matches and restart your shell.

### Linux keyring backend

Both Python's `keyring` library and the Rust binary target the freedesktop
`secret-service` API on Linux. Rust uses pure-Rust zbus to speak the
protocol (no `libdbus-1` system dep required). If you had keyring storage
working under Python, the Rust binary reads the same slot. If you were on
the file fallback (no GNOME Keyring / KWallet daemon), the Rust binary
reads the same `credentials.json` file.

If `zb auth status` returns `"authenticated": false` after install,
double-check:

- The credentials file exists at `$(dirs config_dir)/zoho-books-cli/credentials.json`
- It's 0600
- It contains `client_id`, `client_secret`, `refresh_token`, and `region` at
  minimum

### Rolling back

If something goes wrong and you need the Python version back:

```bash
brew uninstall madisonrickert/tap/zoho-books-cli
uv tool install 'git+https://github.com/madisonrickert/zoho-books-cli@v0.5.0'
```

Credentials persist across the round-trip, so no data loss is possible. The Python
0.5.0 tag remains accessible on GitHub indefinitely.

### Re-authenticating from scratch

If for any reason you want a clean re-auth (e.g. your refresh token was revoked
upstream):

```bash
zb auth logout
zb auth login --client-id ... --client-secret ...
zb org use <organization_id>
```

`zb auth logout` clears both the keyring slot and the file fallback.

## Verification checklist

After install, run these to confirm the drop-in worked:

```bash
zb --version                            # → {"ok":true,"data":{"version":"1.0.0..."}}
zb --list-commands | jq '.data.commands | length'   # → integer (count of leaf commands)
zb auth status                          # → {"ok":true,"data":{"authenticated":true,...}}
zb --dry-run org list                   # → JSON preview, no network call
zb org list                             # → real Zoho API call, returns your orgs
```

If all five succeed without prompting for credentials, the migration is complete.

## Reporting issues

Please [open an issue](https://github.com/madisonrickert/zoho-books-cli/issues)
if anything in the migration doesn't work as documented here. Include:

- Output of `zb --version`
- Output of `which -a zb`
- Operating system (`uname -a`)
- The command that failed and its full stderr output
