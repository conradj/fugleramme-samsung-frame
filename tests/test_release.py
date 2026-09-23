"""Check the distributable archive, rather than its builder internals."""

import importlib.util
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]
MEMBERS = {
    "VERSION", "CHANGELOG.md", "INSTALL.md", "setup.py", "frame-sync.py",
    "requirements.txt", "frame-sync.service", "frame-sync.timer",
    "frame-sync.env.example",
}


class ReleaseTests(unittest.TestCase):
    def test_version_has_matching_changelog_entry(self):
        version = (ROOT / "VERSION").read_text()
        self.assertRegex(version, r"^\d+\.\d+\.\d+\n$")
        headings = re.findall(r"^## \[([^]]+)\]", (ROOT / "CHANGELOG.md").read_text(), re.M)
        self.assertEqual(headings.count(version.strip()), 1)

    def build(self, source, output):
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/build-release.py"),
             "--source-dir", str(source), "--output-dir", str(output)],
            capture_output=True, text=True,
        )

    def fixture(self, location):
        source = location / "source"
        source.mkdir()
        for name in MEMBERS:
            (source / name).write_bytes((ROOT / name).read_bytes())
        return source

    def test_archive_is_complete_small_and_reproducible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "dist"
            version = (ROOT / "VERSION").read_text().strip()
            result = self.build(ROOT, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            archive = output / f"frame-sync-{version}.zip"
            first_bytes = archive.read_bytes()
            self.assertEqual(self.build(ROOT, output).returncode, 0)
            self.assertEqual(archive.read_bytes(), first_bytes)
            with zipfile.ZipFile(archive) as bundle:
                names = bundle.namelist()
                self.assertEqual(set(names), {f"frame-sync-{version}/{name}" for name in MEMBERS})
                self.assertEqual(names, sorted(names))
                for name in MEMBERS:
                    self.assertEqual(bundle.read(f"frame-sync-{version}/{name}"),
                                     (ROOT / name).read_bytes())
                bundle.extractall(root / "unpacked")
            self.assertLess(archive.stat().st_size, 100_000)
            notes = (output / f"release-notes-{version}.md").read_text()
            self.assertTrue(notes.startswith(f"## [{version}] - "))
            self.assertGreater(len(notes.splitlines()), 2)
            self.assertNotIn("## [Unreleased]", notes)
            extracted = root / f"unpacked/frame-sync-{version}"
            spec = importlib.util.spec_from_file_location("release_setup", extracted / "setup.py")
            setup = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(setup)
            with patch.object(setup.sys, "platform", "linux"), \
                    patch.object(setup.os, "geteuid", return_value=0), \
                    patch.object(setup.shutil, "which", return_value="/usr/bin/apt-get"), \
                    patch.object(setup.Path, "is_dir", return_value=True):
                setup.preflight()

    def test_mismatched_changelog_rejects_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.fixture(root)
            (source / "VERSION").write_text("9.9.9\n")
            output = root / "dist"
            result = self.build(source, output)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(list(output.glob("*.zip")) if output.exists() else False)

    def test_missing_member_rejects_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.fixture(root)
            (source / "frame-sync.timer").unlink()
            output = root / "dist"
            result = self.build(source, output)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(list(output.glob("*.zip")) if output.exists() else False)

    def test_malformed_version_rejects_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.fixture(root)
            (source / "VERSION").write_text("v0.1.0\n")
            output = root / "dist"
            result = self.build(source, output)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(list(output.glob("*.zip")) if output.exists() else False)

    def test_empty_changelog_section_rejects_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.fixture(root)
            (source / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-09-23\n")
            output = root / "dist"
            result = self.build(source, output)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(list(output.glob("*.zip")) if output.exists() else False)


if __name__ == "__main__":
    unittest.main()
