"""Static token-cost measurement (Arm A) — Zoho MCP vs ``zb`` CLI.

Counts tokens against Anthropic's `count_tokens` endpoint (free per the
[docs](https://docs.claude.com/en/docs/build-with-claude/token-counting))
for the four cost components a Claude Code session pays:

  1. **Tool catalog** — the schema bundle injected into the system prompt
     when an MCP server is enabled, vs. the ``Bash`` tool the agent already
     has when it uses ``zb``.
  2. **Skill / instructions** — ``SKILL.md`` body for ``zb``, vs. the Zoho
     MCP server's instructions block.
  3. **Per-call payload** — a representative response in zb-envelope form
     vs. raw-MCP form. Uses the synthetic fixtures so this script doesn't
     read live customer data.
  4. **(reserved)** End-to-end task cost lives in ``run_eval.py``.

Outputs ``bench/results_summary_static.json`` (token counts only — no
payload bodies, no IDs, no names; safe to commit per the privacy rules in
the eval plan).

Run:

    export ANTHROPIC_API_KEY=...                # for count_tokens (free)
    uv run bench/capture_schemas.py             # one-time, populates fixtures/zoho_mcp_schemas.json
    uv run bench/measure_static.py              # produces results_summary_static.json
    uv run bench/measure_static.py --model claude-haiku-4-5

The script intentionally degrades gracefully: if the schema fixture is
missing it still reports the components that don't need it, and prints a
note about the missing piece.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parents[1]
BENCH = Path(__file__).resolve().parent
FIXTURES = BENCH / "fixtures"
SYNTH = FIXTURES / "synthetic"

DEFAULT_MODELS = ("claude-sonnet-4-6", "claude-haiku-4-5")

# A minimal "Bash" tool definition representing what the zb path uses. This
# matches the schema Claude Code ships for Bash; we hold it constant across
# both surfaces so the comparison isn't biased by harness-tool overhead.
BASH_TOOL = {
    "name": "Bash",
    "description": (
        "Executes a given bash command in a persistent shell session. The "
        "shell environment is initialized from the user's profile."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The command to execute"},
            "description": {
                "type": "string",
                "description": "Clear, concise description of what this command does",
            },
        },
        "required": ["command"],
    },
}


@dataclass
class Cell:
    """One measurement cell: (component, surface, model) → input_tokens."""

    component: str
    surface: str
    model: str
    input_tokens: int
    notes: str = ""


@dataclass
class Result:
    model_set: tuple[str, ...]
    cells: list[Cell] = field(default_factory=list)

    def add(self, **kw) -> None:
        self.cells.append(Cell(**kw))


def _client() -> anthropic.Anthropic:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("error: set ANTHROPIC_API_KEY (count_tokens is free but needs auth)")
    return anthropic.Anthropic()


def count_tokens_with_tools(
    client: anthropic.Anthropic,
    model: str,
    *,
    tools: list[dict] | None = None,
    system: str | None = None,
    user_message: str = "ping",
) -> int:
    """Count input_tokens for a request shaped like a real tool-use turn.

    We use a placeholder user message so the Messages API accepts the call;
    we only care about the input_tokens delta driven by ``tools`` / ``system``.
    """
    kwargs: dict = {
        "model": model,
        "messages": [{"role": "user", "content": user_message}],
    }
    if tools:
        kwargs["tools"] = tools
    if system:
        kwargs["system"] = system
    resp = client.messages.count_tokens(**kwargs)
    return resp.input_tokens


def load_zoho_mcp_tools() -> list[dict] | None:
    path = FIXTURES / "zoho_mcp_schemas.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["inputSchema"],
        }
        for t in payload["tools"]
    ]


def load_skill_md() -> str:
    return (ROOT / "skills" / "zoho-books" / "SKILL.md").read_text()


# Component #1 — tool catalog
def measure_tool_catalog(client: anthropic.Anthropic, model: str, result: Result) -> None:
    # zb path: just Bash in the toolbelt.
    zb_tokens = count_tokens_with_tools(client, model, tools=[BASH_TOOL])
    # Subtract a no-tool baseline so we report the *marginal* tool-catalog cost.
    baseline = count_tokens_with_tools(client, model)
    result.add(
        component="tool_catalog",
        surface="zb",
        model=model,
        input_tokens=zb_tokens - baseline,
        notes="Bash tool only; zb is reached via Bash.",
    )

    zoho_tools = load_zoho_mcp_tools()
    if zoho_tools is None:
        result.add(
            component="tool_catalog",
            surface="mcp_eager",
            model=model,
            input_tokens=-1,
            notes=(
                "missing fixtures/zoho_mcp_schemas.json — "
                "run `uv run bench/capture_schemas.py` with ZOHO_MCP_URL set"
            ),
        )
        return

    eager = count_tokens_with_tools(client, model, tools=zoho_tools)
    result.add(
        component="tool_catalog",
        surface="mcp_eager",
        model=model,
        input_tokens=eager - baseline,
        notes=f"all {len(zoho_tools)} Zoho MCP tools eagerly loaded.",
    )

    # MCP deferred — what the agent pays at session start with Claude Code's
    # ToolSearch. We approximate by passing the original tool name +
    # description but eliding the input schema (which is what gets fetched
    # on demand). Descriptions are typically the bigger token contribution
    # than schemas, so this approximation is closer to reality than a
    # description-stripped form would be.
    name_only = [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": {"type": "object", "properties": {}},
        }
        for t in zoho_tools
    ]
    deferred = count_tokens_with_tools(client, model, tools=[BASH_TOOL, *name_only])
    result.add(
        component="tool_catalog",
        surface="mcp_deferred",
        model=model,
        input_tokens=deferred - baseline,
        notes=(
            f"name+description only for {len(zoho_tools)} tools (deferred-load "
            "approximation); schemas fetched on demand at additional per-use cost."
        ),
    )


# Component #2 — skill / instructions loading
def measure_skill_loading(client: anthropic.Anthropic, model: str, result: Result) -> None:
    skill = load_skill_md()
    skill_tokens = count_tokens_with_tools(client, model, system=skill)
    baseline = count_tokens_with_tools(client, model)
    result.add(
        component="skill_loading",
        surface="zb",
        model=model,
        input_tokens=skill_tokens - baseline,
        notes=f"SKILL.md = {len(skill)} chars.",
    )
    # MCP path: instructions block is per-server, generally smaller than a
    # full skill. We don't have the Zoho MCP instructions block as a separate
    # artifact; capture_schemas.py could be extended to fetch it. For now,
    # report the absence so the gap is visible.
    result.add(
        component="skill_loading",
        surface="mcp_eager",
        model=model,
        input_tokens=-1,
        notes=(
            "not yet captured; capture_schemas.py would need to fetch the "
            "MCP server's instructions block alongside the tool list."
        ),
    )


# Component #3 — per-call payload (synthetic fixtures only)
def measure_payload(client: anthropic.Anthropic, model: str, result: Result) -> None:
    cases = [
        ("org_get", "org_get.zb.json", "org_get.mcp.json"),
        ("contacts_list", "contacts_list.zb.json", "contacts_list.mcp.json"),
    ]
    for name, zb_file, mcp_file in cases:
        zb_path = SYNTH / zb_file
        mcp_path = SYNTH / mcp_file
        if not zb_path.exists() or not mcp_path.exists():
            continue
        # Compact-normalize both — we measure payload size, not formatting.
        zb_body = json.dumps(json.loads(zb_path.read_text()), separators=(",", ":"))
        mcp_body = json.dumps(json.loads(mcp_path.read_text()), separators=(",", ":"))
        baseline = count_tokens_with_tools(client, model, user_message="x")
        zb_tokens = count_tokens_with_tools(client, model, user_message=zb_body) - baseline
        mcp_tokens = count_tokens_with_tools(client, model, user_message=mcp_body) - baseline
        result.add(
            component=f"payload_{name}",
            surface="zb",
            model=model,
            input_tokens=zb_tokens,
            notes=f"compact JSON, {len(zb_body)} chars.",
        )
        result.add(
            component=f"payload_{name}",
            surface="mcp",
            model=model,
            input_tokens=mcp_tokens,
            notes=f"compact JSON, {len(mcp_body)} chars.",
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        action="append",
        help="Model to measure against. Repeat for multiple. Defaults: sonnet-4-5, haiku-4-5.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=BENCH / "results_summary_static.json",
        help="Output file (default: bench/results_summary_static.json)",
    )
    args = parser.parse_args()

    models = tuple(args.model) if args.model else DEFAULT_MODELS
    client = _client()
    result = Result(model_set=models)

    for model in models:
        print(f"measuring against {model}…", file=sys.stderr)
        measure_tool_catalog(client, model, result)
        measure_skill_loading(client, model, result)
        measure_payload(client, model, result)

    # Pivot to a more legible summary structure for the JSON output.
    summary: dict = {
        "models": list(models),
        "cells": [
            {
                "component": c.component,
                "surface": c.surface,
                "model": c.model,
                "input_tokens": c.input_tokens,
                "notes": c.notes,
            }
            for c in result.cells
        ],
    }
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=False) + "\n")
    print(f"wrote {len(result.cells)} cells to {args.out}", file=sys.stderr)

    # Pretty table to stdout for humans.
    print()
    print(f"{'component':<25} {'surface':<14} {'model':<25} {'tokens':>10}")
    print("-" * 80)
    for c in result.cells:
        toks = "missing" if c.input_tokens < 0 else str(c.input_tokens)
        print(f"{c.component:<25} {c.surface:<14} {c.model:<25} {toks:>10}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
