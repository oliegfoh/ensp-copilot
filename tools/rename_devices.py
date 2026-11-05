#!/usr/bin/env python3
"""Batch-rename device identifiers across plans, fixtures and docs.

The plans and captured console transcripts in this repository are real lab
artifacts. Before publishing, site-specific sysname tags (class / seat
numbers, initials, campus codes, ...) should be replaced with a neutral tag.
Rules are supplied explicitly, so the same tool serves any lab's naming
convention instead of hard-coding one.

Examples:
  # preview what would change
  python tools/rename_devices.py --dry-run --map NP-38=LAB

  # replace one literal tag everywhere
  python tools/rename_devices.py --map NP-38=LAB

  # normalise every R<n>-<tag> device name to a single tag
  python tools/rename_devices.py --suffix LAB

  # several rules at once (applied in order)
  python tools/rename_devices.py --map NP-38=LAB --map "16-xm-=LAB-" --suffix LAB
"""
from __future__ import annotations

import argparse
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
TARGET_DIRS = ("plans", "fixtures", "docs", "topologies", "ensp_copilot", "web", "tests")
EXTRA_FILES = ("README.md",)
TEXT_SUFFIXES = {
    ".json", ".txt", ".md", ".topo", ".svg", ".py", ".toml",
    ".html", ".cfg", ".ini", ".yaml", ".yml",
}


def collect_files() -> list[pathlib.Path]:
    found: set[pathlib.Path] = set()
    for dirname in TARGET_DIRS:
        base = ROOT / dirname
        if base.is_dir():
            found.update(
                p for p in base.rglob("*")
                if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES
            )
    for name in EXTRA_FILES:
        p = ROOT / name
        if p.is_file():
            found.add(p)
    return sorted(found)


def build_rules(maps: list[str], suffix: str | None) -> list[tuple[re.Pattern, str]]:
    rules: list[tuple[re.Pattern, str]] = []
    for item in maps:
        if "=" not in item:
            raise SystemExit(f"invalid --map {item!r}; expected OLD=NEW")
        old, new = item.split("=", 1)
        if not old:
            raise SystemExit("--map OLD must not be empty")
        rules.append((re.compile(re.escape(old)), new))
    if suffix:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", suffix):
            raise SystemExit("--suffix allows only letters, digits, '-' and '_'")
        rules.append((re.compile(r"\bR(\d+)-[A-Za-z0-9_-]+\b"), r"R\1-" + suffix))
    return rules


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", action="append", default=[], metavar="OLD=NEW",
                    help="literal replacement; repeatable")
    ap.add_argument("--suffix", metavar="TAG",
                    help="normalise all R<n>-<tag> device names to TAG")
    ap.add_argument("--dry-run", action="store_true",
                    help="show affected files without writing")
    args = ap.parse_args()

    if not args.map and not args.suffix:
        ap.error("provide at least one --map or --suffix")

    rules = build_rules(args.map, args.suffix)
    changed_files = 0
    total_hits = 0

    for path in collect_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new = text
        hits = 0
        for pattern, replacement in rules:
            new, n = pattern.subn(replacement, new)
            hits += n
        if new == text:
            continue
        changed_files += 1
        total_hits += hits
        rel = path.relative_to(ROOT).as_posix()
        prefix = "[dry-run] " if args.dry_run else ""
        print(f"{prefix}{rel}: {hits} replacement(s)")
        if not args.dry_run:
            # write_bytes keeps LF exactly as read; avoids CRLF churn on Windows
            path.write_bytes(new.encode("utf-8"))

    label = " (dry-run, nothing written)" if args.dry_run else ""
    print(f"\n{total_hits} replacement(s) in {changed_files} file(s){label}")


if __name__ == "__main__":
    main()
