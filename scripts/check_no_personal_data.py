#!/usr/bin/env python3
"""Pre-commit guard: reject staged files containing configured private strings.

Patterns are loaded at runtime from ``scripts/blocked_identifiers.txt``
(per-developer, gitignored; see ``blocked_identifiers.example.txt`` for the
format). If the file is absent, the check is a no-op — the same pattern as
``.secrets.baseline`` for ``detect-secrets``.

Designed as a backstop. The eval harness already gitignores raw API
responses; this catches drift, e.g. someone pasting a live response into a
fixture, doc, or commit message.

Run with the file paths to check:

    scripts/check_no_personal_data.py path1 path2 ...

The pre-commit hook passes staged paths automatically.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PATTERNS_FILE = Path(__file__).resolve().parent / "blocked_identifiers.txt"

# Files we never want to scan (binary, large vendor data).
SKIP_SUFFIXES = {".lock", ".png", ".jpg", ".jpeg", ".gif", ".pdf"}

# Paths exempt from all checks (typically this script's own config templates).
ALLOWLIST = {
    "scripts/blocked_identifiers.example.txt",
    "scripts/check_no_personal_data.py",
}


def _load_patterns(path: Path) -> tuple[list[str], list[re.Pattern[str]]]:
    """Read literal + regex patterns from the config file."""
    if not path.exists():
        return [], []
    literals: list[str] = []
    regexes: list[re.Pattern[str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("literal:"):
            literals.append(line[len("literal:") :])
        elif line.startswith("regex:"):
            regexes.append(re.compile(line[len("regex:") :]))
        else:
            print(
                f"warning: ignoring malformed line in {path.name}: {line!r}",
                file=sys.stderr,
            )
    return literals, regexes


def scan(path: Path, literals: list[str], regexes: list[re.Pattern[str]]) -> list[str]:
    """Return human-readable failure messages for `path`, or empty."""
    if path.suffix in SKIP_SUFFIXES:
        return []
    rel = str(path)
    if rel in ALLOWLIST:
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    failures: list[str] = []
    for needle in literals:
        idx = text.find(needle)
        if idx == -1:
            continue
        line = text.count("\n", 0, idx) + 1
        failures.append(f"  {rel}:{line}: matches a configured blocked literal")
    for pat in regexes:
        m = pat.search(text)
        if m is None:
            continue
        line = text.count("\n", 0, m.start()) + 1
        failures.append(f"  {rel}:{line}: matches a configured blocked pattern")
    return failures


def main(argv: list[str]) -> int:
    literals, regexes = _load_patterns(PATTERNS_FILE)
    if not literals and not regexes:
        return 0  # No config — silently no-op.

    paths = [Path(p) for p in argv[1:] if Path(p).is_file()]
    failures: list[str] = []
    for p in paths:
        failures.extend(scan(p, literals, regexes))
    if failures:
        print("✗ no-personal-data check failed:", file=sys.stderr)
        for f in failures:
            print(f, file=sys.stderr)
        print(
            f"\nMatched a pattern from {PATTERNS_FILE.name}. "
            "Replace the value with a synthetic equivalent, "
            "or update your local pattern list if the rule is wrong.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
