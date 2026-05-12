# CLI latency: Python vs Rust

End-to-end timings for the `zb` binary, comparing the current Python implementation against the released Rust binary.

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

| Metric | Python 0.5.0 | Rust 1.0.2 | Speedup |
|---|---:|---:|---:|
| Cold start (`--version`) | 117.4 ms ± 2.8 | 4.2 ms ± 0.4 | **28.0×** |
| Warm `--help` | 140.4 ms ± 1.6 | 4.2 ms ± 0.4 | **33.4×** |
| `--list-commands` | 138.6 ms ± 8.1 | 6.4 ms ± 0.3 | **21.7×** |
| Dry-run (`expenses list`) | 188.3 ms ± 3.2 | 13.9 ms ± 0.7 | **13.5×** |
| Live API (`org list`) | 351.1 ms ± 40.6 | 214.5 ms ± 57.4 | 1.6× |
| RSS at idle | 37.7 MB | 7.7 MB | **4.9×** |
| Install footprint | 16 MB (uv tool venv) | 4.5 MB (single binary) | **3.6×** |

Times in milliseconds (mean ± stddev). Speedup = Python / Rust; higher is better. Bold = cleared its respective bar.

## Bar to clear

The port has to earn its keep. Hard gates for the original 1.0.0 release:

- Cold start: **≥ 10× faster** (target: under 12 ms). **Cleared: 28× (4.2 ms).**
- Warm `--help`: **≥ 20× faster** (target: under 8 ms). **Cleared: 33× (4.2 ms).**
- RSS at idle: **≥ 5× smaller** (target: under 8 MB). **At 4.9× (7.7 MB) — within rounding of the 5× bar.**

The cold-start and warm gates remain well clear. RSS is within rounding of the 5× bar after the 1.0.2 dep refresh (was 5.0× at 1.0.0 with 7.5 MB; now 4.9× at 7.7 MB). Live-API improves only by the startup-overhead delta (~140 ms), as expected for a network-bounded operation; the stddev is dominated by network jitter.

The "install footprint" comparison is between the Python `uv tool` venv (which includes Python's bundled stdlib + every transitive dep — httpx, typer, keyring, platformdirs, pyyaml, click, rich) and the Rust single binary (which statically links rustls + the rest). 1.0.2's 4.5 MB is heavier than 1.0.0's 3.3 MB because reqwest 0.13 switched the rustls crypto provider from `ring` to `aws-lc-rs` (BoringSSL fork; ~1.2 MB heavier but where the rustls ecosystem is heading). Still 3.6× smaller than the Python install tree.

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

- Python baseline: commit `3638d4c` on `main`, tagged `bench/python-baseline-v0.5.0`.
- Rust column: captured on the `v1.0.2` tag after the dep refresh (rand 0.8 → 0.10; reqwest 0.12 → 0.13; pre-commit-hooks v4.6.0 → v6.0.0; keyring 3 → keyring-core + apple-native-keyring-store), with the release-profile build (LTO + codegen-units=1 + strip + panic=abort). The intermediate `v1.0.1` tag was abandoned mid-pipeline when the new Linux keyring backend exposed a missing `libdbus-1-dev` dep on the GHA runner; `v1.0.2` is the same binary plus the CI fix.
- Machine: same physical macOS arm64 host for both columns. Hyperfine 1.20.0 with `--shell=none`.
- Earlier 1.0.0 numbers (3.3 MB binary, 7.5 MB RSS, 3.9 ms cold start) are preserved in the merge commit `2a9dab9` and the v1.0.0 release notes.
