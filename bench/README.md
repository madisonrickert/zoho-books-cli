# Bench — Zoho MCP vs `zb` CLI token-cost eval

Reproducible measurement of token cost when an LLM agent reaches Zoho Books
through three surfaces:

- **`zb`** — the CLI in this repo, reached via the agent's `Bash` tool with
  `SKILL.md` appended to the system prompt.
- **`mcp_eager`** — Zoho's official Zoho MCP product (the captured Zoho Books toolset, all tools loaded eagerly).
- **`mcp_deferred`** — the same Zoho MCP server with Claude Code's [Tool Search]
  on (default behavior in recent versions): tool *names* load at session
  start, schemas fetch on demand.

[Tool Search]: https://docs.claude.com/en/docs/claude-code/mcp

## What this measures (and what it doesn't)

The numbers below describe **two specific configurations** of two tunable
surfaces:

- **`zb`** as currently shipped — the modules listed in the README, plus
  whatever `SKILL.md` says today. Wrapping more endpoints grows that
  surface; trimming `SKILL.md` shrinks it.
- **Zoho MCP** as the operator running the eval has it configured. The
  Zoho MCP is *configurable* — exposing 5 tools or 250 tools is a setting,
  not a property of the protocol. The schemas captured in
  `fixtures/zoho_mcp_schemas.json` are one snapshot.

The captured snapshot covers 104 Zoho MCP tools — chosen by the user
running the eval to roughly match `zb`'s wrapped surface so the comparison
isn't between a maximalist MCP and a minimalist CLI. A different user's MCP,
with a different tool selection, will produce different ratios.

What the eval *can* tell you, treating these as data points:

- The token cost of *this particular* MCP catalog at full eager-load.
- The reduction Tool Search delivers on *that* catalog.
- The per-task token / dollar cost of running the corpus through each
  surface as configured.
- The fact that the JSON envelopes are functionally equivalent — that
  one *is* invariant across configurations.

What it *can't* tell you:

- That MCP is universally more or less expensive than a CLI.
- That this CLI is universally cheaper than any MCP.
- What ratios you'll see at *your* tool count, *your* skill body, *your*
  task corpus.

Run it against your own setup if you want numbers for your config.

## Headline numbers (one configuration, n=5)

**Static cost** — what each surface adds to context every turn, measured via
Anthropic `count_tokens` (exact, free):

| | `zb` | MCP eager | MCP w/ Tool Search |
| --- | ---: | ---: | ---: |
| Tool catalog | 600 | 82,353 | 6,207 |
| Skill / instructions | 3,891 (`SKILL.md`) | — | — |
| Payload, `org get` | 818 | 819 | 819 |
| Payload, `contacts list` | 2,185 | 2,186 | 2,186 |
| **Total surface tax** | **4,491** | **82,353** | **6,207** |

The payload row is a wash: zb's `{"ok":true,"data":…}` and the MCP
`{"code":0,"message":"success",…}` envelope tokenize within 1 token. The
interesting line is the catalog. Against the realistic baseline — Tool
Search enabled, the modern Claude Code default — `zb`'s 4,491-token surface
tax is **~28% slimmer** than the 6,207-token Zoho MCP catalog. Without Tool
Search (eager loading), MCP balloons to 82,353 tokens, an 18× gap that only
shows up if a client opts out of tool discovery — increasingly rare.

**End-to-end cost** — n=5 per cell, 50 zb runs + 50 MCP runs, Claude Code
headless (`claude -p`), `claude-haiku-4-5` + `claude-sonnet-4-6`, both arms
with `--strict-mcp-config --disable-slash-commands` for isolation. Cost is the
model-reported `total_cost_usd`.

> **Lower is better** in `$` and `turns` columns; 🟢 marks the winning surface
> of each pair. **Ratio columns** (`MCP / zb cost`, `MCP / zb turns`):
> > 1× means MCP cost more / took more turns (🟢 favors zb); < 1× favors MCP.

| Task | Model | zb $ | MCP $ | zb turns | MCP turns | MCP / zb cost | MCP / zb turns |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| T1 — org get | Haiku | 🟢 0.036 | 0.062 | 3.4 | 🟢 2.0 | 🟢 1.71× | 0.59× |
| T1 | Sonnet | 0.070 | 🟢 0.063 | 🟢 3.0 | 3.2 | 0.90× | 🟢 1.07× |
| T2 — contacts list | Haiku | 🟢 0.058 | 0.075 | 8.8 | 🟢 5.6 | 🟢 1.29× | 0.64× |
| T2 | Sonnet | 🟢 0.088 | 0.101 | 🟢 2.4 | 5.6 | 🟢 1.15× | 🟢 2.33× |
| T3 — multi-step | Haiku | 🟢 0.059 | 0.063 | 8.0 | 🟢 4.2 | 🟢 1.06× | 0.53× |
| T3 | Sonnet | 🟢 0.069 | 0.122 | 🟢 2.8 | 7.6 | 🟢 1.77× | 🟢 2.71× |
| T4 — invoices list | Haiku | 🟢 0.052 | 0.054 | 6.6 | 🟢 4.0 | 🟢 1.04× | 0.61× |
| T4 | Sonnet | 🟢 0.085 | 0.142 | 🟢 2.8 | 8.2 | 🟢 1.67× | 🟢 2.93× |
| T5 — dry-run | Haiku | 🟢 0.026 | 0.043 | 🟢 1.4 | 2.4 | 🟢 1.67× | 🟢 1.71× |
| T5 | Sonnet | 🟢 0.083 | 0.098 | 🟢 3.6 | 4.4 | 🟢 1.18× | 🟢 1.22× |

For this corpus / configuration / `n=5`: MCP came in higher than zb in 9 of
the 10 cells, geometric-mean cost ratio 1.32. At a different MCP tool count,
a different `SKILL.md` body, or a different task mix the ratio could move
either direction. Where the gap widens (mostly on Sonnet, where the model is
otherwise efficient) the 82K-token catalog dominates each turn; where it
narrows (Haiku) MCP's schema-validated calls finish in fewer turns, partially
offsetting the catalog tax.

Full per-cell stats — `mean / median / p95 / stddev / 95% CI half-width` —
are in [`results_summary.json`](results_summary.json). Static-arm details are
in [`results_summary_static.json`](results_summary_static.json).

## Two arms

The eval is split so most of the work runs free.

| Arm | What it measures | Cost |
| --- | --- | --- |
| **A. Static** (`measure_static.py`) | Tool catalog tokens, skill / instructions tokens, per-call payload tokens. Uses Anthropic's `count_tokens` endpoint, [free per the docs](https://docs.claude.com/en/docs/build-with-claude/token-counting). | $0 (free RPM-limited endpoint). Needs `ANTHROPIC_API_KEY`. |
| **B. Live** (`run_eval.py`) | End-to-end task cost: `usage.{input,output,cache_*}_tokens`, `total_cost_usd`, `num_turns`. Drives `claude -p` headless. | $0 on a Pro/Max subscription. The harness shells out to `claude -p` which uses your local OAuth credential. |

## Reproduce

```bash
# 1. Install bench deps.
uv pip install -e ".[bench]"

# 2. Static arm (free).
export ANTHROPIC_API_KEY=...        # any non-zero balance; count_tokens is free.
export ZOHO_MCP_URL='https://...'   # one-time browser OAuth on first capture.
uv run bench/capture_schemas.py     # writes bench/fixtures/zoho_mcp_schemas.json
uv run bench/measure_static.py      # writes bench/results_summary_static.json

# 3. Live arm (free on Pro/Max). Run from a *plain terminal* — see "Gotchas".
uv run bench/run_eval.py --task all --surface zb mcp_eager --model haiku sonnet --n 5
uv run bench/summarize.py bench/results/runs_*.jsonl
```

The published baseline numbers above came from `--n 5`. Higher `n` tightens
the CIs but takes proportionally longer wall time.

## Test corpus

Five tasks, all read-only. Locked in `tasks.py`; changing them bumps `CORPUS_VERSION`.

| ID | Description |
| --- | --- |
| T1 | Single-record read, small payload (`org get`). |
| T2 | List read, medium payload (`contacts list --per-page 5`). |
| T3 | Multi-step: search vendors → list expenses → get one. Exercises 19-digit ID round-tripping. |
| T4 | List read, large payload (`invoices list --per-page 5`). |
| T5 | Composed-verb dry-run: build a payment-application request without committing. |

## Experimental design

- **n** is configurable via `--n`; the published baseline used n=5 per
  (task × surface × model × cache-state). The eval plan calls for n=20
  to tighten 95% CIs to ~10% half-width — adopt that for any
  README-grade republication.
- **Models**: `claude-sonnet-4-6` and `claude-haiku-4-5` by default.
- **Cache states**: `warm` only. The `cold` axis was specified in the eval
  plan but the harness does not yet sleep past the cache TTL between cold
  cells, so running them today would be identical to warm and produce
  misleading numbers. `cold` will be re-added once that sleep is
  implemented; until then the warm path is the only one published, which
  is also what users actually pay in steady-state Claude Code use.
- **Surfaces**: `zb`, `mcp_eager`, `mcp_deferred` (see top). Today
  `mcp_deferred` and `mcp_eager` use the same `claude -p` invocation —
  Claude Code auto-decides based on context budget — so the live-arm
  distinction lives in the static-arm catalog comparison only.

## Output contract

- `bench/results/<timestamp>.jsonl` — one row per run. **Gitignored**;
  contains live API token counts but never the model's free-text reply.
- `bench/results_summary.json` — committed. Aggregate stats per cell:
  `mean / median / p95 / stddev / ci95_half`. Plus a `deltas` block
  expressing each MCP surface as a ratio of `zb` for the same task / model /
  cache-state.

## Gotchas

1. **Run the live arm from a plain terminal**, not from inside an existing
   Claude Code session. Headless `claude -p` would otherwise inherit
   ambient skills, MCP servers, and CLAUDE.md context — that pollutes the
   measurement and inflates token counts. Open a fresh shell, `cd` to a
   neutral directory, then run.
2. **MCP eager vs deferred is determined by Claude Code's Tool Search
   default**. As of writing, Tool Search is on by default once the MCP tool
   list exceeds 10% of context. Recording surface as `mcp_deferred` reflects
   intent; the absolute measurement is whatever Claude Code does in that
   release.
3. **No live mutating tests.** All five tasks read-only. T5 is constructed
   so the model builds a request body but never submits it — the `zb` arm
   uses `--dry-run`, the MCP arms have no equivalent so the model is
   instructed not to call.
4. **No payloads in `results_summary.json`.** Token counts and dollar costs
   only — no contact names, IDs, or amounts. The `pre-commit` hook
   `no-personal-data` is the backstop if drift sneaks in.
5. **JSON formatting matters.** When comparing payload size, both surfaces
   are normalized to compact JSON inside the harness.
6. **Per-org variance.** Real responses depend on the user's data shape
   (custom fields, line-item counts). Two reviewers running the eval
   against different orgs will get different absolute numbers but the
   surface-to-surface ratios should track.

## Privacy

- `bench/results/` is gitignored — raw runs include token counts derived
  from your live data.
- Synthetic fixtures at `bench/fixtures/synthetic/` mirror Zoho's response
  *shape* but use fully fake names and 9999-prefixed IDs.
- A pre-commit hook (`scripts/check_no_personal_data.py`) scans staged
  files against patterns in `scripts/blocked_identifiers.txt` (per-developer,
  gitignored). See `scripts/blocked_identifiers.example.txt` for the format.

## Why this exists

The 2026 wave of MCP-vs-CLI posts ([OnlyCLI](https://onlycli.github.io/OnlyCLI/blog/mcp-token-cost-benchmark/),
[Scalekit](https://www.scalekit.com/blog/mcp-vs-cli-use), [Speakeasy](https://www.speakeasy.com/blog/how-we-reduced-token-usage-by-100x-dynamic-toolsets-v2),
[BSWEN](https://docs.bswen.com/blog/2026-04-24-mcp-token-overhead/)) reports
figures from 4× to 160× without disclosing run counts, confidence intervals,
caching state, or model controls. This eval is the same comparison with
explicit n, two model families, and the harness committed in-repo for
independent reproduction. Run it against your own Zoho org and post the
JSONL summary if your numbers differ.
