"""Root Typer app + error handling + --list-commands introspection.

Installed as `zb` and `zoho-books` entry points. Every command writes a single
JSON object to stdout on success; typed `ZohoCLIError` exceptions are caught
here and serialized to stderr with a meaningful exit code.
"""

from __future__ import annotations

import sys

import click
import httpx
import typer

from zoho_books_cli import __version__, output
from zoho_books_cli.commands import (
    auth,
    bank_transactions,
    bills,
    chart_of_accounts,
    contacts,
    customer_payments,
    expenses,
    invoices,
    org,
    projects,
    recurring_expenses,
)
from zoho_books_cli.commands.raw import raw as raw_command
from zoho_books_cli.errors import EXIT_UNKNOWN, NetworkError, ZohoCLIError

app = typer.Typer(
    help=(
        "Agent-first CLI for Zoho Books. Full coverage of expenses, recurring "
        "expenses, bank transactions, customer payments, projects, contacts, "
        "and chart of accounts, plus binary uploads for receipts and "
        "attachments. Outputs JSON on stdout; errors are JSON on stderr with "
        "meaningful exit codes. See AGENTS.md."
    ),
    no_args_is_help=True,
    add_completion=False,
)

app.add_typer(auth.app, name="auth")
app.add_typer(org.app, name="org")
app.add_typer(expenses.app, name="expenses")
app.add_typer(recurring_expenses.app, name="recurring-expenses")
app.add_typer(bank_transactions.app, name="bank-transactions")
app.add_typer(bills.app, name="bills")
app.add_typer(invoices.app, name="invoices")
app.add_typer(customer_payments.app, name="customer-payments")
app.add_typer(projects.app, name="projects")
app.add_typer(contacts.app, name="contacts")
app.add_typer(chart_of_accounts.app, name="chart-of-accounts")
app.command("raw", help="Call any Zoho Books v3 endpoint directly.")(raw_command)


def _version_callback(value: bool) -> None:
    if value:
        output.emit_success({"version": __version__})
        raise typer.Exit()


def _list_commands_callback(value: bool) -> None:
    if not value:
        return
    tree = _walk_group(typer.main.get_command(app), prefix="")
    output.emit_success({"commands": tree})
    raise typer.Exit()


@app.callback()
def _root(
    pretty: bool = typer.Option(
        False,
        "--pretty",
        help="Human-readable output (requires the 'rich' extra).",
    ),
    version: bool = typer.Option(
        None,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the CLI version as JSON and exit.",
    ),
    list_commands: bool = typer.Option(
        None,
        "--list-commands",
        callback=_list_commands_callback,
        is_eager=True,
        help="Print the full command tree as JSON and exit.",
    ),
) -> None:
    output.set_pretty(pretty)


def _walk_group(group: click.Command, *, prefix: str) -> list[dict]:
    result: list[dict] = []
    if isinstance(group, click.Group):
        for name, cmd in sorted(group.commands.items()):
            full = f"{prefix} {name}".strip()
            if isinstance(cmd, click.Group):
                result.extend(_walk_group(cmd, prefix=full))
            else:
                result.append(
                    {
                        "name": full,
                        "summary": (cmd.help or "").strip().split("\n")[0],
                        "params": [_describe_param(p) for p in cmd.params],
                    }
                )
    return result


def _describe_param(p: click.Parameter) -> dict:
    return {
        "name": p.name,
        "kind": "argument" if isinstance(p, click.Argument) else "option",
        "required": bool(getattr(p, "required", False)),
        "opts": list(getattr(p, "opts", []) or []),
        "help": getattr(p, "help", None),
    }


def main() -> None:
    """Entry point. Wraps the Typer app with the CLI's error contract."""
    try:
        app(standalone_mode=False)
    except ZohoCLIError as e:
        output.emit_error(e.to_payload())
        sys.exit(e.exit_code)
    except click.exceptions.Exit as e:
        sys.exit(e.exit_code)
    except click.exceptions.UsageError as e:
        output.emit_error(
            {
                "ok": False,
                "error": {
                    "code": "validation",
                    "message": str(e),
                    "details": {},
                },
            }
        )
        sys.exit(3)
    except httpx.RequestError as e:
        err = NetworkError(f"Network error: {e}")
        output.emit_error(err.to_payload())
        sys.exit(err.exit_code)
    except KeyboardInterrupt:
        output.emit_error(
            {
                "ok": False,
                "error": {"code": "unknown", "message": "Interrupted.", "details": {}},
            }
        )
        sys.exit(EXIT_UNKNOWN)
    except Exception as e:  # last-resort; keep the output contract intact
        output.emit_error(
            {
                "ok": False,
                "error": {
                    "code": "unknown",
                    "message": f"{type(e).__name__}: {e}",
                    "details": {},
                },
            }
        )
        sys.exit(EXIT_UNKNOWN)


if __name__ == "__main__":
    main()
