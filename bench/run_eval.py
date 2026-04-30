"""End-to-end eval harness (Arm B) — Zoho MCP vs ``zb`` CLI.

Drives ``claude -p`` (Claude Code in headless / print mode) for each
(task * surface * model * cache-state) cell. Headless ``claude`` reads
the OAuth subscription credential from the local keychain, so a Pro/Max
user pays nothing per run.

Per surface we tweak ``claude``'s flags so the model gets exactly the
tools and instructions we want to measure, and nothing else:

  - **zb**: only Bash is allowed; ``SKILL.md`` is appended to the system
    prompt; no MCP servers are loaded.
  - **mcp_eager**: an MCP config file enables the Zoho MCP server with
    all its tools allowed; SKILL.md is *not* loaded.
  - **mcp_deferred**: same MCP config, but tools start name-only and
    fetch on demand (Claude Code's Tool Search behavior).

For each run we capture the JSON Claude Code emits (``--output-format
json``), which contains ``usage.{input_tokens,output_tokens,cache_*}``,
``total_cost_usd``, ``num_turns``, and ``duration_ms``. We sum nothing
— Claude Code already aggregates per-session totals in that JSON.

Output: one JSONL row per run to ``bench/results/<timestamp>.jsonl``.
``summarize.py`` aggregates the JSONL into ``results_summary.json``.

Run:

    # Set ZOHO_MCP_URL once if you want the MCP arms (otherwise zb-only).
    export ZOHO_MCP_URL='https://...'
    uv run bench/run_eval.py --task T1 T2 --surface zb --model haiku --n 3

    # Full sweep:
    uv run bench/run_eval.py --task all --surface all --model sonnet haiku --n 20

The harness is intentionally a thin wrapper over ``claude -p`` so the
measurement matches what a real Claude Code user pays. **Do not run this
inside an existing Claude Code session** — the parent context's
auto-loaded skills and MCP servers will pollute the child's prompt. Run
from a plain terminal, with ``cd`` set to a clean directory.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import subprocess
import sys
import time
from collections.abc import Iterable
from pathlib import Path

from tasks import CACHE_STATES, CORPUS_VERSION, DEFAULT_MODELS, SURFACES, TASKS, Task

ROOT = Path(__file__).resolve().parents[1]
BENCH = Path(__file__).resolve().parent
RESULTS = BENCH / "results"
SKILL_MD = ROOT / "skills" / "zoho-books" / "SKILL.md"

# Model alias → full id passed to `claude --model`. We resolve aliases
# locally (rather than passing the alias through) so the `model` field on
# every JSONL row records the *exact* version the run measured. Bump these
# when newer point releases ship.
MODEL_ALIASES = {
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-7",
}


@dataclasses.dataclass
class CellSpec:
    task: Task
    surface: str
    model: str
    cache_state: str
    iter_index: int


def _model_id(name: str) -> str:
    return MODEL_ALIASES.get(name, name)


def _mcp_config(zoho_mcp_url: str) -> dict:
    """Build a minimal MCP config that connects only the Zoho server.

    We deliberately do NOT use the user's ambient Claude Code MCP config
    — we want the surface to contain *only* Zoho tools (so the eval
    isn't measuring overhead from the user's other MCP servers).
    """
    return {
        "mcpServers": {
            "zoho-books": {
                "type": "http",
                "url": zoho_mcp_url,
            }
        }
    }


def _build_command(spec: CellSpec, cwd: Path, mcp_config_path: Path | None) -> list[str]:
    """Translate a (task, surface, model, …) cell into a ``claude -p`` argv.

    Isolation flags below are critical for reproducibility — without them
    the harness inherits whichever MCP servers, skills, and CLAUDE.md the
    operator has installed locally, which would inflate every measurement
    by tens of thousands of tokens of ambient context.
    """
    cmd: list[str] = [
        "claude",
        "-p",
        spec.task.prompt,
        "--model",
        _model_id(spec.model),
        "--output-format",
        "json",
        "--no-session-persistence",
        "--exclude-dynamic-system-prompt-sections",
        # Block ambient MCP servers — only the configs we explicitly pass apply.
        "--strict-mcp-config",
        # Block ambient skills (auto-loaded via /name triggers).
        "--disable-slash-commands",
    ]

    if spec.surface == "zb":
        cmd += [
            "--allowedTools",
            "Bash",
            "--append-system-prompt-file",
            str(SKILL_MD),
        ]
    elif spec.surface in ("mcp_eager", "mcp_deferred"):
        if mcp_config_path is None:
            raise RuntimeError(
                f"surface {spec.surface} needs ZOHO_MCP_URL to be set so an "
                "MCP config can be built."
            )
        cmd += ["--mcp-config", str(mcp_config_path)]
        # Wildcard-allow Zoho MCP tools so the model can call them without
        # interactive permission prompts.
        cmd += ["--allowedTools", "mcp__zoho-books__*"]
        # Deferred vs eager: today both rely on Claude Code's default
        # behavior (Tool Search auto-enables once the MCP catalog exceeds
        # the context budget threshold). The label distinguishes intent so
        # the summary can compare them once Claude Code exposes a flag to
        # force eager-vs-deferred explicitly.
    else:
        raise ValueError(f"unknown surface {spec.surface!r}")

    return cmd


def _run_one(spec: CellSpec, cwd: Path, mcp_config_path: Path | None) -> dict:
    cmd = _build_command(spec, cwd, mcp_config_path)
    started = time.time()
    base_record: dict = {
        "task_id": spec.task.id,
        "surface": spec.surface,
        "model": _model_id(spec.model),
        "cache_state": spec.cache_state,
        "iter": spec.iter_index,
        "corpus_version": CORPUS_VERSION,
    }
    # 600s per-run cap. Empirically a long Haiku loop on a list-style task
    # can run 5+ minutes; pad to 10 to avoid spurious kills, but bound it
    # so a stuck `claude -p` doesn't hold up the whole sweep indefinitely.
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            **base_record,
            "wall_seconds": round(time.time() - started, 3),
            "exit_code": -1,
            "error": "subprocess timed out (>600s)",
        }
    elapsed = time.time() - started

    record: dict = {
        **base_record,
        "wall_seconds": round(elapsed, 3),
        "exit_code": proc.returncode,
    }

    if proc.returncode != 0 or not proc.stdout.strip():
        # Store stderr only — stdout on the failure path can include the
        # model's free-text reply, which would echo live record names / IDs
        # into a (gitignored, but still local-on-disk) JSONL file.
        record["error"] = (proc.stderr or "(no stderr; stdout suppressed)")[-2000:]
        return record

    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        # Same reason as above — don't quote stdout, just the parse error.
        record["error"] = f"non-json stdout: {e}"
        return record

    # Pull out only the fields we want — *not* the model's free-text
    # `result` (that field can quote contact names / IDs from live data).
    record["usage"] = result.get("usage", {})
    record["total_cost_usd"] = result.get("total_cost_usd", 0)
    record["num_turns"] = result.get("num_turns", 0)
    record["duration_ms"] = result.get("duration_ms", 0)
    record["duration_api_ms"] = result.get("duration_api_ms", 0)
    record["service_tier"] = result.get("usage", {}).get("service_tier", "")
    return record


def _iter_cells(
    tasks: Iterable[Task],
    surfaces: Iterable[str],
    models: Iterable[str],
    cache_states: Iterable[str],
    n: int,
) -> Iterable[CellSpec]:
    for task in tasks:
        for surface in surfaces:
            for model in models:
                for cache_state in cache_states:
                    for i in range(n):
                        yield CellSpec(task, surface, model, cache_state, i)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--task",
        nargs="+",
        default=["all"],
        help="Task IDs to run (T1..T5) or 'all'. Default: all.",
    )
    parser.add_argument(
        "--surface",
        nargs="+",
        default=["all"],
        choices=["all", *SURFACES],
        help="Surfaces to compare. Default: all.",
    )
    parser.add_argument(
        "--model",
        nargs="+",
        default=list(DEFAULT_MODELS),
        help=f"Model aliases or full IDs. Default: {' '.join(DEFAULT_MODELS)}.",
    )
    parser.add_argument(
        "--cache",
        choices=list(CACHE_STATES),
        default=CACHE_STATES[0],
        help=(
            "Cache state to measure. Currently 'warm' only — 'cold' "
            "requires a TTL-busting sleep that the harness does not yet "
            "implement (running cold today would be identical to warm)."
        ),
    )
    parser.add_argument(
        "--n",
        type=int,
        default=20,
        help="Iterations per cell. Default: 20.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSONL path. Default: bench/results/<timestamp>.jsonl",
    )
    args = parser.parse_args()

    tasks = TASKS if "all" in args.task else [t for t in TASKS if t.id in args.task]
    if not tasks:
        print(f"error: no matching tasks for {args.task!r}", file=sys.stderr)
        return 2

    surfaces = list(SURFACES) if "all" in args.surface else args.surface
    cache_states = [args.cache]

    zoho_mcp_url = os.environ.get("ZOHO_MCP_URL")
    mcp_config_path: Path | None = None
    if any(s.startswith("mcp_") for s in surfaces):
        if not zoho_mcp_url:
            print(
                "error: surfaces include MCP arms but ZOHO_MCP_URL is unset.\n"
                "       set the env var or restrict --surface to zb.",
                file=sys.stderr,
            )
            return 2
        cfg_dir = BENCH / ".cache"
        cfg_dir.mkdir(exist_ok=True)
        mcp_config_path = cfg_dir / "mcp_config.json"
        mcp_config_path.write_text(json.dumps(_mcp_config(zoho_mcp_url)))

    RESULTS.mkdir(exist_ok=True)
    out = args.out or (RESULTS / f"runs_{int(time.time())}.jsonl")
    cwd = BENCH / ".cache"
    cwd.mkdir(exist_ok=True)

    # Refuse to overwrite a non-empty file. A previous detached sweep
    # writing to the same path while a new one starts will produce
    # interleaved JSON lines that look like single rows but are corrupt;
    # opting in via --append or a fresh path makes the choice explicit.
    if out.exists() and out.stat().st_size > 0:
        print(
            f"error: {out} already exists and is non-empty.\n"
            "       remove it, pass --out to a fresh path, or check that no "
            "prior sweep is still running (`ps -ef | grep run_eval`).",
            file=sys.stderr,
        )
        return 2

    total = sum(1 for _ in _iter_cells(tasks, surfaces, args.model, cache_states, args.n))
    print(f"running {total} cells → {out}", file=sys.stderr)

    with out.open("w") as fh:
        for i, spec in enumerate(
            _iter_cells(tasks, surfaces, args.model, cache_states, args.n), start=1
        ):
            print(
                f"[{i}/{total}] {spec.task.id} surface={spec.surface} "
                f"model={spec.model} cache={spec.cache_state} iter={spec.iter_index}",
                file=sys.stderr,
            )
            record = _run_one(spec, cwd, mcp_config_path)
            fh.write(json.dumps(record) + "\n")
            fh.flush()

    print(f"done. summarize with: uv run bench/summarize.py {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
