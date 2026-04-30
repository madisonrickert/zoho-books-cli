"""Aggregate JSONL runs from ``run_eval.py`` into ``results_summary.json``.

Privacy-preserving by design: reads only the per-run *token counts*,
*cost*, *turn count*, and *wall time* — not the model's free-text
output. The summary file is safe to commit; raw JSONL is not (it's
gitignored under ``bench/results/``).

Output cell shape:

    {
      "task_id": "T1",
      "surface": "zb",
      "model": "claude-sonnet-4-5",
      "cache_state": "warm",
      "n": 20,
      "input_tokens":  {"mean": …, "median": …, "p95": …, "stddev": …, "ci95_half": …},
      "output_tokens": {…},
      "cache_read_input_tokens":     {…},
      "cache_creation_input_tokens": {…},
      "total_cost_usd": {…},
      "num_turns": {…},
      "wall_seconds": {…}
    }

Ratios (zb vs each MCP surface) are computed from cell means and
included in a ``deltas`` block.

Run:

    uv run bench/summarize.py bench/results/runs_<timestamp>.jsonl
    # writes bench/results_summary.json
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

BENCH = Path(__file__).resolve().parent

# Fields we'll aggregate. Each is dotted-path into the JSONL row.
NUMERIC_FIELDS = [
    ("input_tokens", "usage.input_tokens"),
    ("output_tokens", "usage.output_tokens"),
    ("cache_read_input_tokens", "usage.cache_read_input_tokens"),
    ("cache_creation_input_tokens", "usage.cache_creation_input_tokens"),
    ("total_cost_usd", "total_cost_usd"),
    ("num_turns", "num_turns"),
    ("wall_seconds", "wall_seconds"),
]


def _dig(row: dict, dotted: str) -> Any:
    cur: Any = row
    for piece in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(piece)
    return cur


def _stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    n = len(values)
    mean = statistics.fmean(values)
    median = statistics.median(values)
    sorted_vals = sorted(values)
    p95 = sorted_vals[max(0, math.ceil(0.95 * n) - 1)]
    sd = statistics.stdev(values) if n > 1 else 0.0
    # 95% CI half-width using normal approximation (n>=20 is the design point).
    ci95_half = 1.96 * sd / math.sqrt(n) if n > 1 else 0.0
    return {
        "n": n,
        "mean": round(mean, 4),
        "median": round(median, 4),
        "p95": round(p95, 4),
        "stddev": round(sd, 4),
        "ci95_half": round(ci95_half, 4),
    }


def aggregate(rows: list[dict]) -> list[dict]:
    """Group rows by (task,surface,model,cache_state); compute stats per cell."""
    bucket: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        if "error" in row:
            continue
        key = (
            row.get("task_id"),
            row.get("surface"),
            row.get("model"),
            row.get("cache_state"),
        )
        if any(k is None for k in key):
            continue
        bucket[key].append(row)

    cells: list[dict] = []
    for key, entries in sorted(bucket.items()):
        task_id, surface, model, cache_state = key
        cell: dict = {
            "task_id": task_id,
            "surface": surface,
            "model": model,
            "cache_state": cache_state,
            "n_runs": len(entries),
        }
        for out_name, dotted in NUMERIC_FIELDS:
            vals: list[float] = []
            for r in entries:
                v = _dig(r, dotted)
                if isinstance(v, int | float):
                    vals.append(float(v))
            cell[out_name] = _stats(vals)
        cells.append(cell)
    return cells


def compute_deltas(cells: list[dict]) -> list[dict]:
    """For each (task,model,cache_state), express MCP cells as a ratio of zb."""
    by_key: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for c in cells:
        by_key[(c["task_id"], c["model"], c["cache_state"])][c["surface"]] = c

    deltas: list[dict] = []
    for key, surfaces in sorted(by_key.items()):
        task_id, model, cache_state = key
        zb = surfaces.get("zb")
        if zb is None:
            continue
        for surface_name, cell in surfaces.items():
            if surface_name == "zb":
                continue
            row: dict = {
                "task_id": task_id,
                "model": model,
                "cache_state": cache_state,
                "surface": surface_name,
            }
            for fld in ("input_tokens", "output_tokens", "total_cost_usd", "num_turns"):
                z = zb.get(fld, {}).get("mean")
                m = cell.get(fld, {}).get("mean")
                if z and m and z != 0:
                    row[f"{fld}_ratio_vs_zb"] = round(m / z, 3)
                    row[f"{fld}_zb_mean"] = z
                    row[f"{fld}_{surface_name}_mean"] = m
            deltas.append(row)
    return deltas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, nargs="+", help="One or more JSONL run files")
    parser.add_argument(
        "--out",
        type=Path,
        default=BENCH / "results_summary.json",
        help="Output JSON file (default: bench/results_summary.json)",
    )
    args = parser.parse_args()

    rows: list[dict] = []
    for path in args.input:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))

    cells = aggregate(rows)
    deltas = compute_deltas(cells)
    # Pull corpus_version from the first non-error row — every run records
    # it, so all rows from the same sweep should agree.
    corpus_versions = sorted({r["corpus_version"] for r in rows if "corpus_version" in r})
    surfaces_present = sorted({c["surface"] for c in cells})
    surfaces_expected = ["zb", "mcp_eager", "mcp_deferred"]
    surfaces_missing = [s for s in surfaces_expected if s not in surfaces_present]
    summary = {
        "schema_version": 1,
        "corpus_versions": corpus_versions,
        "n_total_runs": sum(c["n_runs"] for c in cells),
        "n_errors": sum(1 for r in rows if "error" in r),
        "surfaces_present": surfaces_present,
        # If a surface is missing, the file represents a partial sweep —
        # consumers should not interpret absent cells as zero or as "not
        # measured." Pair this with --surface all when running the harness.
        "surfaces_missing": surfaces_missing,
        "cells": cells,
        "deltas": deltas,
    }
    args.out.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"wrote {len(cells)} cells, {len(deltas)} deltas → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
