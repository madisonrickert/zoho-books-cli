#!/usr/bin/env bash
# Capture CLI latency benchmarks for the current `zb` binary.
#
# Usage:
#   ZB_BIN=/path/to/zb ./run.sh <label>
#   ./run.sh python-0.5.0
#   ZB_BIN=/Users/madison/Developer/zoho-books-cli/target/release/zb ./run.sh rust-1.0.0
#
# Outputs raw hyperfine JSON + supporting captures into ./raw/<label>/.
# That directory is gitignored — only the summarised RESULTS.md is committed.

set -euo pipefail

LABEL="${1:-default}"
ZB_BIN="${ZB_BIN:-$(command -v zb)}"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="${HERE}/raw/${LABEL}"
mkdir -p "${OUT_DIR}"

echo "Benchmarking : ${ZB_BIN}"
echo "Label        : ${LABEL}"
echo "Output dir   : ${OUT_DIR}"
echo

# --- Microbenchmarks (no network) ------------------------------------------
hyperfine --shell=none --warmup 0 --runs 50 \
  --export-json "${OUT_DIR}/cold-start.json" \
  "${ZB_BIN} --version"

hyperfine --shell=none --warmup 5 --runs 50 \
  --export-json "${OUT_DIR}/warm-help.json" \
  "${ZB_BIN} --help"

hyperfine --shell=none --warmup 5 --runs 50 \
  --export-json "${OUT_DIR}/list-commands.json" \
  "${ZB_BIN} --list-commands"

hyperfine --shell=none --warmup 5 --runs 50 \
  --export-json "${OUT_DIR}/dry-run.json" \
  "${ZB_BIN} --dry-run expenses list"

# --- Network-bounded (real Zoho API) ---------------------------------------
hyperfine --shell=none --warmup 3 --runs 20 \
  --export-json "${OUT_DIR}/live-api.json" \
  "${ZB_BIN} org list"

# --- RSS (max resident set size at idle) -----------------------------------
# /usr/bin/time -l is BSD/macOS; on Linux use -v.
/usr/bin/time -l "${ZB_BIN}" --version >/dev/null 2>"${OUT_DIR}/rss.txt"

# --- Install footprint -----------------------------------------------------
{
  echo "label=${LABEL}"
  echo "binary=${ZB_BIN}"
  if command -v uv >/dev/null 2>&1 && uv tool dir 2>/dev/null | xargs -I{} test -d "{}/zoho-books-cli"; then
    UV_TOOL_DIR="$(uv tool dir)/zoho-books-cli"
    echo "install-tree=${UV_TOOL_DIR}"
    echo "install-tree-size=$(du -sh "${UV_TOOL_DIR}" | awk '{print $1}')"
    echo "install-tree-bytes=$(du -sk "${UV_TOOL_DIR}" | awk '{print $1*1024}')"
  fi
  echo "binary-bytes=$(wc -c < "${ZB_BIN}" | tr -d ' ')"
} > "${OUT_DIR}/size.txt"

echo
echo "Done. Raw outputs in ${OUT_DIR}/"
