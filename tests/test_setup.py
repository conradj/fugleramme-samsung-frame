"""Exercise setup with temporary files and a mocked OS command boundary."""

import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


class SetupTests(unittest.TestCase):
    def setUp(self):
        script = Path(__file__).resolve().parents[1] / "setup.py"
        self.assertTrue(script.exists(), "The guided setup command is missing")
        spec = importlib.util.spec_from_file_location("frame_setup", script)
        self.setup = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.setup)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.setup.CONFIG = self.root / "frame-sync.env"
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def test_new_config_uses_defaults_and_private_permissions(self):
        with patch("builtins.input", side_effect=["192.168.1.42", ""]):
            self.setup.configure()
        self.assertEqual(self.setup.CONFIG.read_text(),
                         "TV_HOST=192.168.1.42\n"
                         "FUGLERAMME_URL=http://127.0.0.1:8080\n"
                         "FRAME_SYNC_STATE_DIR=/var/lib/frame-sync\n"
                         "TV_TOKEN_FILE=/var/lib/frame-sync/tv-token.txt\n")
        self.assertEqual(self.setup.CONFIG.stat().st_mode & 0o777, 0o600)

    def test_rerun_preserves_existing_settings_without_prompting(self):
        original = "TV_HOST=existing-tv\nTV_TOKEN_FILE=/custom/token.txt\n"
        self.setup.CONFIG.write_text(original)
        with patch("builtins.input", side_effect=AssertionError("Unexpected prompt")):
            self.setup.configure()
        self.assertEqual(self.setup.CONFIG.read_text(), original)

    def test_failed_config_save_leaves_no_partial_file_and_can_be_retried(self):
        with patch("builtins.input", side_effect=["frame.local", ""]):
            with patch.object(self.setup.os, "fsync", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    self.setup.configure()
        self.assertFalse(self.setup.CONFIG.exists())
        self.assertEqual(list(self.root.iterdir()), [])
        with patch("builtins.input", side_effect=["frame.local", ""]):
            self.setup.configure()
        self.assertIn("TV_HOST=frame.local\n", self.setup.CONFIG.read_text())

    def test_invalid_addresses_are_reprompted_before_writing_config(self):
        with patch("builtins.input", side_effect=[
            "http://tv:8002", "frame.local", "http://host/\nTV_HOST=other",
            "ftp://host", "http://birds.local:8080/",
        ]):
            self.setup.configure()
        self.assertIn("TV_HOST=frame.local\n", self.setup.CONFIG.read_text())
        self.assertIn("FUGLERAMME_URL=http://birds.local:8080\n",
                      self.setup.CONFIG.read_text())

    def test_timer_enabled_only_after_confirmed_picture(self):
        with patch.object(self.setup.subprocess, "run") as run:
            with patch("builtins.input", side_effect=["", "y"]):
                self.assertTrue(self.setup.pair_and_test())
        commands = [call.args[0] for call in run.call_args_list]
        self.assertLess(commands.index(["systemctl", "start", "frame-sync.service"]),
                        commands.index(["systemctl", "enable", "--now", "frame-sync.timer"]))

    def test_skipped_sync_can_be_retried_without_enabling_timer(self):
        with patch.object(self.setup.subprocess, "run") as run:
            with patch("builtins.input", side_effect=["", "n", "q"]):
                self.assertFalse(self.setup.pair_and_test())
        self.assertFalse(any("enable" in call.args[0] for call in run.call_args_list))

    def test_failed_sync_does_not_offer_success_or_enable_timer(self):
        def execute(command, **kwargs):
            if command == ["systemctl", "start", "frame-sync.service"]:
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0)

        with patch.object(self.setup.subprocess, "run", side_effect=execute) as run:
            with patch("builtins.input", side_effect=["", "q"]):
                self.assertFalse(self.setup.pair_and_test())
        self.assertFalse(any("enable" in call.args[0] for call in run.call_args_list))

    def test_unsupported_platform_stops_before_installing(self):
        with patch.object(self.setup.sys, "platform", "darwin"):
            with patch.object(self.setup.subprocess, "run") as run:
                with self.assertRaisesRegex(RuntimeError, "Linux"):
                    self.setup.preflight()
        run.assert_not_called()

    def test_archive_preflight_points_to_online_manual_guide(self):
        with patch.object(self.setup.sys, "platform", "linux"), \
                patch.object(self.setup.os, "geteuid", return_value=0), \
                patch.object(self.setup.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "https://github.com/conradj/fugleramme-samsung-frame/blob/main/docs/advanced.md"):
                self.setup.preflight()

    def test_update_waits_for_running_sync_and_preserves_runtime_files(self):
        self.setup.UNITS = self.root / "units"
        self.setup.UNITS.mkdir()
        (self.setup.UNITS / "frame-sync.timer").touch()
        self.setup.STATE = self.root / "state"
        self.setup.STATE.mkdir()
        token = self.setup.STATE / "tv-token.txt"
        token.write_text("existing-token")
        state = self.setup.STATE / "state.json"
        state.write_text('{"content_id":"previous-art"}')
        self.setup.APP = self.root / "app"
        activity = iter(["activating\n", "inactive\n"])

        def execute(command, **kwargs):
            if command[:2] == ["systemctl", "show"]:
                return subprocess.CompletedProcess(command, 0, stdout=next(activity))
            return subprocess.CompletedProcess(command, 0)

        with patch.object(self.setup.subprocess, "run", side_effect=execute) as run:
            with patch.object(self.setup.pwd, "getpwnam", return_value=object()):
                with patch.object(self.setup.time, "sleep"):
                    self.setup.install()
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[0], ["systemctl", "disable", "--now", "frame-sync.timer"])
        self.assertEqual(commands[1][:2], ["systemctl", "show"])
        self.assertEqual(commands[2][:2], ["systemctl", "show"])
        self.assertEqual(commands[3], ["apt-get", "update"])
        self.assertFalse(any("enable" in command for command in commands))
        self.assertEqual(token.read_text(), "existing-token")
        self.assertEqual(state.read_text(), '{"content_id":"previous-art"}')

    def test_reuses_token_with_service_account_ownership(self):
        self.setup.STATE = self.root / "state"
        self.setup.STATE.mkdir()
        source = self.root / "old-token.txt"
        source.write_text("existing-token")
        with patch("builtins.input", return_value=str(source)):
            with patch.object(self.setup.subprocess, "run") as run:
                self.setup.reuse_token()
        self.assertEqual(run.call_args.args[0], [
            "install", "-o", "frame-sync", "-g", "frame-sync", "-m", "600",
            str(source), str(self.setup.STATE / "tv-token.txt"),
        ])

    def test_existing_token_is_never_overwritten(self):
        self.setup.STATE = self.root
        (self.root / "tv-token.txt").write_text("keep-this-token")
        with patch("builtins.input", side_effect=AssertionError("Unexpected prompt")):
            with patch.object(self.setup.subprocess, "run") as run:
                self.setup.reuse_token()
        run.assert_not_called()
        self.assertEqual((self.root / "tv-token.txt").read_text(), "keep-this-token")


if __name__ == "__main__":
    unittest.main()
