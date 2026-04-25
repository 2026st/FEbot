#!/usr/bin/env python3
"""Check synchronization between code, .env.example, and README.md."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / "README.md"
ENV_EXAMPLE_PATH = ROOT / ".env.example"
SOURCE_DIRS = (ROOT / "src", ROOT / "scripts")

ENV_USAGE_PATTERNS = (
    re.compile(r'os\.environ\.get\(\s*["\']([A-Z][A-Z0-9_]*)["\']'),
    re.compile(r'os\.environ\[\s*["\']([A-Z][A-Z0-9_]*)["\']\s*\]'),
    re.compile(r'getenv\(\s*["\']([A-Z][A-Z0-9_]*)["\']'),
)
ENV_LINE_PATTERN = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=")
COMMENTED_ENV_LINE_PATTERN = re.compile(r"^\s*#\s*([A-Z][A-Z0-9_]*)\s*=")
README_KEY_PATTERN = re.compile(r"`([A-Z][A-Z0-9_]*)`")


def collect_env_keys_from_code() -> set[str]:
    keys: set[str] = set()
    for source_dir in SOURCE_DIRS:
        if not source_dir.exists():
            continue
        for path in source_dir.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for pattern in ENV_USAGE_PATTERNS:
                keys.update(pattern.findall(text))
    return keys


def parse_env_example() -> tuple[set[str], set[str]]:
    active_keys: set[str] = set()
    all_keys: set[str] = set()
    for raw_line in ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        active_match = ENV_LINE_PATTERN.match(line)
        if active_match:
            key = active_match.group(1)
            active_keys.add(key)
            all_keys.add(key)
            continue
        commented_match = COMMENTED_ENV_LINE_PATTERN.match(line)
        if commented_match:
            all_keys.add(commented_match.group(1))
    return active_keys, all_keys


def parse_readme_env_keys() -> set[str]:
    text = README_PATH.read_text(encoding="utf-8")
    return set(README_KEY_PATTERN.findall(text))


def main() -> int:
    code_keys = collect_env_keys_from_code()
    active_example_keys, all_example_keys = parse_env_example()
    readme_keys = parse_readme_env_keys()

    missing_in_example = sorted(code_keys - all_example_keys)
    missing_in_readme = sorted(code_keys - readme_keys)
    stale_active_example = sorted(active_example_keys - code_keys)

    has_error = False
    if missing_in_example:
        has_error = True
        print("[sync-check] Missing in .env.example:")
        for key in missing_in_example:
            print(f"  - {key}")

    if missing_in_readme:
        has_error = True
        print("[sync-check] Missing in README.md env section:")
        for key in missing_in_readme:
            print(f"  - {key}")

    if stale_active_example:
        has_error = True
        print("[sync-check] Active keys in .env.example not used in code:")
        for key in stale_active_example:
            print(f"  - {key}")

    if has_error:
        print(
            "\n[sync-check] Failed. Keep code, README.md, and .env.example in sync."
        )
        return 1

    print("[sync-check] OK: code, README.md, and .env.example are synchronized.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
