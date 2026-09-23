#!/usr/bin/env python3
"""Build a deterministic, allowlisted install ZIP and release notes."""

import argparse
from pathlib import Path
import re
import sys
import zipfile


MEMBERS = (
    "VERSION", "CHANGELOG.md", "INSTALL.md", "LICENSE", "setup.py", "frame-sync.py",
    "requirements.txt", "frame-sync.service", "frame-sync.timer",
    "frame-sync.env.example",
)
ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def release_data(source):
    version_bytes = (source / "VERSION").read_bytes()
    if not re.fullmatch(rb"[0-9]+\.[0-9]+\.[0-9]+\n", version_bytes):
        raise ValueError("VERSION must contain MAJOR.MINOR.PATCH and one newline")
    version = version_bytes.decode("ascii").strip()
    changelog = (source / "CHANGELOG.md").read_text(encoding="utf-8")
    matches = list(re.finditer(rf"^## \[{re.escape(version)}\][ \t]+-[ \t]+\d{{4}}-\d{{2}}-\d{{2}}[ \t]*$", changelog, re.M))
    if len(matches) != 1:
        raise ValueError(f"CHANGELOG.md needs exactly one ## [{version}] heading")
    next_heading = re.search(r"^## \[", changelog[matches[0].end():], re.M)
    end = matches[0].end() + next_heading.start() if next_heading else len(changelog)
    if not changelog[matches[0].end():end].strip():
        raise ValueError(f"CHANGELOG.md has no changes for {version}")
    notes = changelog[matches[0].start():end].strip() + "\n"
    return version, notes


def build(source, output):
    source = source.resolve()
    # Validate every input before touching the output directory.
    payload = {}
    for name in MEMBERS:
        payload[name] = (source / name).read_bytes()
    version, notes = release_data(source)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"frame-sync-{version}.zip"
    temporary = output / f".{archive.name}.tmp"
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            for name in sorted(MEMBERS):
                info = zipfile.ZipInfo(f"frame-sync-{version}/{name}", ZIP_TIME)
                info.create_system = 3
                info.external_attr = 0o644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                bundle.writestr(info, payload[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        with zipfile.ZipFile(temporary) as bundle:
            expected = {f"frame-sync-{version}/{name}" for name in MEMBERS}
            if set(bundle.namelist()) != expected or bundle.testzip() is not None:
                raise ValueError("archive validation failed")
        temporary.replace(archive)
        (output / f"release-notes-{version}.md").write_text(notes, encoding="utf-8")
    finally:
        temporary.unlink(missing_ok=True)
    print(archive)
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path, default=Path("dist"))
    args = parser.parse_args()
    try:
        build(args.source_dir, args.output_dir)
    except (OSError, UnicodeError, ValueError) as error:
        print(f"release build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
