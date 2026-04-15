# Contributing

## Dev setup

Using [uv](https://docs.astral.sh/uv/) (recommended):

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
pre-commit install
```

Or with stdlib + pip:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

## Running tests & lint

```bash
pytest
ruff check
ruff format --check
detect-secrets scan --baseline .secrets.baseline
```

All four must pass before pushing.

## Adding a new command group

1. Create `src/zoho_books_cli/commands/<group>.py` exposing a `typer.Typer()` instance named `app`.
2. Register it in `src/zoho_books_cli/cli.py` via `app.add_typer(...)`.
3. Every command must:
   - Accept `--pretty` (inherited from the root app).
   - Return a single JSON object via `output.emit_success(...)`.
   - Raise typed exceptions from `errors.py`; never print errors directly.
4. Add tests in `tests/test_<group>.py` using `respx` to mock HTTP.

## Commit hygiene

- Never commit tokens, `.env`, or `credentials.json`. The pre-commit hook will block most cases, but double-check with `git diff --cached` before committing.
- Conventional-style prefixes (`feat:`, `fix:`, `docs:`) are appreciated but not required.
