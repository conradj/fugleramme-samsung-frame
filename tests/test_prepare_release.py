"""Exercise the version and changelog changes made for merged PRs."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/prepare-release.py"


class PrepareReleaseTests(unittest.TestCase):
    def prepare(self, root, number, title):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--source-dir", str(root),
             "--pr-number", str(number), "--title", title, "--date", "2026-09-24"],
            capture_output=True, text=True,
        )

    def test_merge_advances_patch_and_adds_release_notes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "VERSION").write_text("0.1.1\n")
            (root / "CHANGELOG.md").write_text(
                "# Changelog\n\n## [Unreleased]\n\n## [0.1.1] - 2026-09-23\n\n- Earlier change.\n"
            )
            result = self.prepare(root, 3, "Improve TV pairing")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "0.1.2")
            self.assertEqual((root / "VERSION").read_text(), "0.1.2\n")
            self.assertEqual((root / "CHANGELOG.md").read_text(),
                "# Changelog\n\n## [Unreleased]\n\n"
                "## [0.1.2] - 2026-09-24\n\n- Improve TV pairing (#3).\n\n"
                "## [0.1.1] - 2026-09-23\n\n- Earlier change.\n")

    def test_rerun_keeps_version_and_notes_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "VERSION").write_text("0.1.2\n")
            notes = "# Changelog\n\n## [Unreleased]\n\n## [0.1.2] - 2026-09-24\n\n- Improve TV pairing (#3).\n"
            (root / "CHANGELOG.md").write_text(notes)
            result = self.prepare(root, 3, "Improve TV pairing")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "0.1.2")
            self.assertEqual((root / "CHANGELOG.md").read_text(), notes)

    def test_malformed_version_does_not_change_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "VERSION").write_text("bad\n")
            notes = "# Changelog\n\n## [Unreleased]\n"
            (root / "CHANGELOG.md").write_text(notes)
            result = self.prepare(root, 3, "Improve TV pairing")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((root / "VERSION").read_text(), "bad\n")
            self.assertEqual((root / "CHANGELOG.md").read_text(), notes)


if __name__ == "__main__":
    unittest.main()
