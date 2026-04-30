"""Read-only task corpus for the MCP-vs-CLI eval.

Five fixed tasks chosen to span small / large payloads and single-step /
multi-step tool-use loops. Locked **before** measurement so the eval can't
be cherry-picked: changing this file invalidates prior runs and bumps the
corpus version.

All tasks read-only. Mutating verbs are out of scope; the dry-run probe
(T5) exercises the request-construction path without contacting Zoho.

The corpus is consumed by ``run_eval.py``. ``surfaces`` lists the tool
configurations to compare.
"""

from __future__ import annotations

from dataclasses import dataclass

CORPUS_VERSION = 1


@dataclass(frozen=True)
class Task:
    id: str
    description: str
    prompt: str
    notes: str = ""


TASKS: list[Task] = [
    Task(
        id="T1",
        description="Single-record read, small payload.",
        prompt=(
            "Look up the current Zoho Books organization and tell me its name "
            "and base currency. Reply with just one sentence."
        ),
    ),
    Task(
        id="T2",
        description="List read, medium payload.",
        prompt=(
            "List the 5 most recently created contacts in Zoho Books. "
            "Return a bullet list of contact name and contact type."
        ),
    ),
    Task(
        id="T3",
        description=(
            "Multi-step: search vendors, list their expenses, get one — "
            "exercises ID round-tripping."
        ),
        prompt=(
            "Find the most recent expense charged to a vendor whose name "
            "contains 'OpenAI'. Return the date, amount, and the expense ID."
        ),
    ),
    Task(
        id="T4",
        description="List read, large payload (line items per invoice).",
        prompt=(
            "Summarize the 5 most recently created invoices in Zoho Books. "
            "For each: invoice number, customer name, status, balance."
        ),
    ),
    Task(
        id="T5",
        description=(
            "Composed-verb dry-run: build the request to apply a $100 "
            "credit-note payment toward an invoice without committing. "
            "Tests whether the surface can preview a write without "
            "performing it."
        ),
        prompt=(
            "Build (do NOT submit) the request that would apply a $100 "
            "payment from credit-note CN-DRYRUN to invoice INV-DRYRUN. "
            "Show me the request body you would send."
        ),
        notes=(
            "On the zb side this is `--dry-run` on `invoices credits apply`; "
            "the MCP side has no equivalent dry-run, so the model is asked "
            "to construct (not call) the request."
        ),
    ),
]


SURFACES = (
    "zb",  # Bash + SKILL.md, no MCP
    "mcp_eager",  # Zoho MCP server with all tools loaded
    "mcp_deferred",  # Zoho MCP server with ToolSearch deferred loading
)


#: Cache states the harness will sweep over. "cold" was in the original
#: design (5-min idle to invalidate the cache TTL) but is not yet
#: implemented — running cold cells today is identical to warm and would
#: produce misleading numbers. Re-add "cold" once the harness sleeps past
#: the cache TTL between cells of that label.
CACHE_STATES = ("warm",)

#: Default model list — exact IDs so JSONL rows record the precise
#: version measured. Update in lockstep with run_eval.MODEL_ALIASES when
#: new point releases ship.
DEFAULT_MODELS = ("claude-sonnet-4-6", "claude-haiku-4-5")
