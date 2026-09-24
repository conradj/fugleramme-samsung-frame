#!/usr/bin/env python3
"""Advance the patch version and record one merged PR in the changelog."""

import argparse
from datetime import date
from pathlib import Path
import re
import sys


def prepare(source, pr_number, title, released_on):
    version_file = source / "VERSION"
    changelog_file = source / "CHANGELOG.md"
    version_text = version_file.read_text(encoding="ascii")
    changelog = changelog_file.read_text(encoding="utf-8")
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)\n", version_text)
    if not match:
        raise ValueError("VERSION must contain MAJOR.MINOR.PATCH and one newline")
    version = version_text.strip()
    if len(re.findall(rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}$", changelog, re.M)) != 1:
        raise ValueError(f"CHANGELOG.md needs exactly one section for {version}")
    if not changelog.startswith("# Changelog\n\n## [Unreleased]\n\n"):
        raise ValueError("CHANGELOG.md needs an empty Unreleased section")

    marker = f"(#{pr_number})"
    existing = re.findall(rf"(?m)^- .*{re.escape(marker)}\.?$", changelog)
    if existing:
        if len(existing) != 1:
            raise ValueError(f"PR #{pr_number} occurs more than once in CHANGELOG.md")
        position = changelog.index(existing[0])
        headings = list(re.finditer(r"^## \[([^]]+)\] - \d{4}-\d{2}-\d{2}$", changelog[:position], re.M))
        if not headings:
            raise ValueError(f"PR #{pr_number} has no release section")
        return headings[-1].group(1)

    clean_title = " ".join(title.split()).rstrip(".")
    if not clean_title:
        raise ValueError("PR title is empty")
    major, minor, patch = map(int, match.groups())
    next_version = f"{major}.{minor}.{patch + 1}"
    heading = f"## [{next_version}] - {released_on.isoformat()}\n\n"
    entry = f"- {clean_title} {marker}.\n\n"
    prefix = "# Changelog\n\n## [Unreleased]\n\n"
    changelog_file.write_text(prefix + heading + entry + changelog[len(prefix):], encoding="utf-8")
    version_file.write_text(next_version + "\n", encoding="ascii")
    return next_version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    try:
        if args.pr_number <= 0:
            raise ValueError("PR number must be positive")
        print(prepare(args.source_dir, args.pr_number, args.title, args.date))
    except (OSError, UnicodeError, ValueError) as error:
        print(f"release preparation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
