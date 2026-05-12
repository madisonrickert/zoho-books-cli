# CLI latency: Python vs Rust

End-to-end timings for the `zb` binary, comparing the current Python implementation against the Rust port (work-in-progress on branch `port/rust`).

Captured with `bench/cli-latency/run.sh`. Tooling: [hyperfine](https://github.com/sharkdp/hyperfine) 1.20.0. macOS arm64 (M-series). All runs use `--shell=none` to exclude shell-wrapper overhead.

Raw `hyperfine` JSON exports are kept under `bench/cli-latency/raw/<label>/` and gitignored — only the aggregated numbers in this file are committed.

## Methodology

| Metric | Tool / Command | Runs |
|---|---|---|
| Cold start | `hyperfine --warmup 0 --runs 50 'zb --version'` | 50, no warmup |
| Warm `--help` | `hyperfine --warmup 5 --runs 50 'zb --help'` | 50 + 5 warmup |
| `--list-commands` | `hyperfine --warmup 5 --runs 50 'zb --list-commands'` | 50 + 5 warmup |
| Dry-run round-trip | `hyperfine --warmup 5 --runs 50 'zb --dry-run expenses list'` | 50 + 5 warmup |
| Live API round-trip | `hyperfine --warmup 3 --runs 20 'zb org list'` | 20 + 3 warmup (real Zoho) |
| RSS at idle | `/usr/bin/time -l zb --version` (max resident set size) | single |
| Install footprint | `du -sh` of the install tree (Python: full uv tool venv; Rust: single binary) | single |

## Results

| Metric | Python 0.5.0 | Rust 1.0.0 | Speedup |
|---|---:|---:|---:|
| Cold start (`--version`) | 117.4 ms ± 2.8 | _pending_ | _pending_ |
| Warm `--help` | 140.4 ms ± 1.6 | _pending_ | _pending_ |
| `--list-commands` | 138.6 ms ± 8.1 | _pending_ | _pending_ |
| Dry-run (`expenses list`) | 188.3 ms ± 3.2 | _pending_ | _pending_ |
| Live API (`org list`) | 351.1 ms ± 40.6 | _pending_ | _pending_ |
| RSS at idle | 37.7 MB | _pending_ | _pending_ |
| Install footprint | 16 MB | _pending_ | _pending_ |

Times in milliseconds (mean ± stddev). Speedup = Python / Rust; higher is better.

## Bar to clear

The port has to earn its keep. Hard gates for merge:

- Cold start: **≥ 10× faster** (target: under 12 ms).
- Warm `--help`: **≥ 20× faster** (target: under 8 ms).
- RSS at idle: **≥ 5× smaller** (target: under 8 MB).

If any of these miss, surface in the pre-merge review and decide whether to land anyway or block.

The live-API benchmark is network-bounded, so the Rust column there is expected to improve only by the startup-overhead delta (~110 ms), not proportionally. Useful as a sanity check, not a primary gate.

## Reproducing

```bash
# Python (from main or any commit pre-port):
ZB_BIN=$(command -v zb) ./run.sh python-<version>

# Rust (from port/rust after a release build):
cargo build --release
ZB_BIN=./target/release/zb ./run.sh rust-<version>
```

Each invocation writes timings to `raw/<label>/`. Update the table above by hand from `hyperfine`'s mean/stddev output.

## Provenance

- Python baseline: commit captured during `port/rust` planning, tagged `bench/python-baseline-v0.5.0`.
- Rust column: filled in once the port reaches feature parity on `port/rust`, before the Python tree is deleted.
- Machine: same physical macOS arm64 host for both columns; otherwise the comparison is uncalibrated.
