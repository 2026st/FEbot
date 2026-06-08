#!/usr/bin/env python3
"""Run the same quality gates as .github/workflows/ci-cd.yml locally."""

from __future__ import annotations

import argparse
import subprocess
import sys

RUFF_TARGETS = ["src", "scripts", "tests"]


def run(cmd: list[str]) -> int:
    print("+", " ".join(cmd), flush=True)
    return subprocess.call(cmd)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Local CI checks (mirrors GitHub Actions lint job + pytest).",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Run ruff format and ruff check --fix before verification.",
    )
    args = parser.parse_args()
    py = sys.executable

    if args.fix:
        if run([py, "-m", "ruff", "format", *RUFF_TARGETS]) != 0:
            return 1
        if run([py, "-m", "ruff", "check", "--fix", *RUFF_TARGETS]) != 0:
            return 1

    steps = [
        [py, "scripts/check_sync.py"],
        [py, "-m", "ruff", "format", "--check", *RUFF_TARGETS],
        [py, "-m", "ruff", "check", *RUFF_TARGETS],
        [py, "-m", "pytest"],
    ]
    for cmd in steps:
        if run(cmd) != 0:
            return 1
    print("ci_local: all checks passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
