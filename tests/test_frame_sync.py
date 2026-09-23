"""Offline tests: replace only the external TV and HTTP boundaries."""

import importlib.util
import io
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch


SCRIPT = Path(__file__).resolve().parents[1] / "frame-sync.py"


class FrameSyncTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.env = patch.dict(os.environ, {
            "HOME": str(self.root),
            "TV_HOST": "frame.example.test",
            "FRAME_SYNC_STATE_DIR": str(self.root / "state"),
            "TV_TOKEN_FILE": str(self.root / "token.txt"),
        }, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.tv_class = Mock()
        dependency = types.ModuleType("samsungtvws")
        dependency.SamsungTVWS = self.tv_class
        exceptions = types.ModuleType("samsungtvws.exceptions")
        exceptions.ConnectionFailure = type("ConnectionFailure", (Exception,), {})
        exceptions.ResponseError = type("ResponseError", (Exception,), {})
        self.exceptions = exceptions
        dependency.exceptions = exceptions
        self.modules = patch.dict(sys.modules, {"samsungtvws": dependency,
                                               "samsungtvws.exceptions": exceptions})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def load(self):
        spec = importlib.util.spec_from_file_location("frame_sync", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_missing_host_fails_before_network_or_state_creation(self):
        os.environ.pop("TV_HOST")
        module = self.load()
        with patch.object(module, "fetch_json") as fetch:
            with self.assertRaisesRegex(ValueError, "TV_HOST"):
                module.synchronize()
            fetch.assert_not_called()
        self.assertFalse((self.root / "state").exists())

    def test_invalid_retry_count_fails_before_network(self):
        os.environ["FRAME_SYNC_RETRIES"] = "0"
        module = self.load()
        with patch.object(module, "fetch_json") as fetch:
            with self.assertRaisesRegex(ValueError, "FRAME_SYNC_RETRIES"):
                module.synchronize()
            fetch.assert_not_called()

    def test_default_state_is_saved_under_current_home(self):
        os.environ.pop("FRAME_SYNC_STATE_DIR")
        os.environ.pop("TV_TOKEN_FILE")
        module = self.load()
        # Avoid touching any real home directory when running against old code.
        self.assertTrue(module.STATE_DIR.is_relative_to(self.root))
        module.STATE_DIR.mkdir(parents=True)
        module.save_state("revision-1", "new-art")
        self.assertEqual(module.load_state()["content_id"], "new-art")
        self.assertTrue(module.TOKEN_FILE.is_relative_to(self.root))

    def test_unchanged_collage_does_not_contact_tv(self):
        module = self.load()
        module.STATE_DIR.mkdir()
        module.save_state("revision-1", "old-art")
        with patch.object(module, "fetch_json", return_value={"token": "revision-1"}):
            module.synchronize()
        self.tv_class.assert_not_called()

    def test_art_mode_off_keeps_collage_pending(self):
        module = self.load()
        self.tv_class.return_value.art.return_value.get_artmode.return_value = "off"
        with patch.object(module, "fetch_json", return_value={"token": "revision-1"}), \
                patch.object(module, "download") as download:
            module.synchronize()
        download.assert_not_called()
        self.assertFalse(module.STATE_FILE.exists())

    def test_success_records_new_art_and_deletes_only_previous_upload(self):
        module = self.load()
        module.STATE_DIR.mkdir()
        module.save_state("revision-1", "old-art")
        art = self.tv_class.return_value.art.return_value
        art.get_artmode.return_value = "on"
        art.get_current.return_value = {
            "event": "current_artwork", "content_id": "old-art",
            "matte_id": "none", "portrait_matte_id": "none",
        }
        art.upload.return_value = "new-art"
        with patch.object(module, "fetch_json", return_value={"token": "revision-2"}), \
                patch.object(module, "download"):
            module.synchronize()
        art.select_image.assert_called_once_with("new-art", show=True)
        art.delete.assert_called_once_with("old-art")
        self.assertEqual(json.loads(module.STATE_FILE.read_text())["token"], "revision-2")
        self.assertEqual(module.load_state()["content_id"], "new-art")

    def test_current_managed_artwork_matte_is_used_for_new_upload(self):
        module, art = self.prepare_update()
        # samsungtvws 3.0.6 get_current() returns the decoded D2D payload:
        # content_id and matte_id, with portrait_matte_id when reported by the TV.
        art.get_current.return_value = {
            "event": "current_artwork", "content_id": "old-art",
            "matte_id": "shadowbox_polar", "portrait_matte_id": "flexible_polar",
        }
        module.synchronize()
        art.upload.assert_called_once_with(str(module.IMAGE_FILE),
                                           matte="shadowbox_polar",
                                           portrait_matte="flexible_polar")
        art.select_image.assert_called_once_with("new-art", show=True)
        art.delete.assert_called_once_with("old-art")

    def test_current_managed_artwork_with_no_matte_keeps_none(self):
        module, art = self.prepare_update()
        art.get_current.return_value = {
            "event": "current_artwork", "content_id": "old-art",
            "matte_id": "none", "portrait_matte_id": "none",
        }
        module.synchronize()
        art.upload.assert_called_once_with(str(module.IMAGE_FILE),
                                           matte="none", portrait_matte="none")

    def test_missing_portrait_matte_defaults_to_none(self):
        module, art = self.prepare_update()
        art.get_current.return_value = {
            "event": "current_artwork", "content_id": "old-art",
            "matte_id": "shadowbox_polar",
        }
        module.synchronize()
        art.upload.assert_called_once_with(str(module.IMAGE_FILE),
                                           matte="shadowbox_polar",
                                           portrait_matte="none")

    def test_unrelated_current_artwork_matte_is_not_copied(self):
        module, art = self.prepare_update()
        art.get_current.return_value = {
            "event": "current_artwork", "content_id": "unrelated-art",
            "matte_id": "shadowbox_polar", "portrait_matte_id": "flexible_polar",
        }
        module.synchronize()
        art.upload.assert_called_once_with(str(module.IMAGE_FILE),
                                           matte="none", portrait_matte="none")

    def test_first_upload_does_not_read_current_artwork(self):
        module = self.load()
        art = self.tv_class.return_value.art.return_value
        art.get_artmode.return_value = "on"
        art.upload.return_value = "new-art"
        with patch.object(module, "fetch_json", return_value={"token": "revision-1"}), \
                patch.object(module, "download"):
            module.synchronize()
        art.get_current.assert_not_called()
        art.upload.assert_called_once_with(str(module.IMAGE_FILE),
                                           matte="none", portrait_matte="none")

    def test_incomplete_current_artwork_matte_falls_back(self):
        module, art = self.prepare_update()
        for metadata in (
            {"event": "current_artwork", "content_id": "old-art"},
            {"event": "current_artwork", "content_id": "old-art", "matte_id": ""},
            {"event": "current_artwork", "content_id": "old-art", "matte_id": 7},
            {"event": "current_artwork", "content_id": "old-art", "matte_id": "none",
             "portrait_matte_id": 7},
            None,
        ):
            with self.subTest(metadata=metadata):
                module.save_state("revision-1", "old-art")
                art.reset_mock()
                art.get_current.return_value = metadata
                module.synchronize()
                art.upload.assert_called_with(str(module.IMAGE_FILE),
                                              matte="none", portrait_matte="none")

    def test_current_artwork_read_retries_then_uploads_without_matte(self):
        module, art = self.prepare_update()
        art.get_current.side_effect = self.exceptions.ResponseError("bad response")
        with self.assertLogs(module.LOG, level="WARNING") as logs:
            module.synchronize()
        self.assertEqual(art.get_current.call_count, 2)
        art.upload.assert_called_once_with(str(module.IMAGE_FILE),
                                           matte="none", portrait_matte="none")
        self.assertIn("matte", " ".join(logs.output).lower())

    def test_transient_current_artwork_read_failure_recovers(self):
        module, art = self.prepare_update()
        art.get_current.side_effect = [self.exceptions.ConnectionFailure("busy"), {
            "event": "current_artwork", "content_id": "old-art",
            "matte_id": "shadowbox_polar", "portrait_matte_id": "none",
        }]
        module.synchronize()
        self.assertEqual(art.get_current.call_count, 2)
        art.upload.assert_called_once_with(str(module.IMAGE_FILE),
                                           matte="shadowbox_polar",
                                           portrait_matte="none")

    def test_unexpected_matte_read_error_is_visible(self):
        module, art = self.prepare_update()
        art.get_current.side_effect = RuntimeError("programming error")
        with self.assertRaisesRegex(RuntimeError, "programming error"):
            module.synchronize()
        art.upload.assert_not_called()

    def prepare_update(self):
        module = self.load()
        module.STATE_DIR.mkdir()
        module.save_state("revision-1", "old-art")
        art = self.tv_class.return_value.art.return_value
        art.get_artmode.return_value = "on"
        art.get_current.return_value = {
            "event": "current_artwork", "content_id": "old-art",
            "matte_id": "none", "portrait_matte_id": "none",
        }
        art.upload.return_value = "new-art"
        art.delete.return_value = True
        fetch = patch.object(module, "fetch_json", return_value={"token": "revision-2"})
        fetch.start()
        self.addCleanup(fetch.stop)
        download = patch.object(module, "download")
        download.start()
        self.addCleanup(download.stop)
        return module, art

    def test_failed_commit_preserves_both_images_and_recovers_without_upload(self):
        module, art = self.prepare_update()
        save = module.save_state

        def fail_commit(token, *args, **kwargs):
            if token == "revision-2":
                raise OSError("disk full")
            return save(token, *args, **kwargs)

        with patch.object(module, "save_state", side_effect=fail_commit):
            with self.assertRaises(OSError):
                module.synchronize()
        art.delete.assert_not_called()
        self.assertEqual(module.load_state()["content_id"], "old-art")
        module.synchronize()
        art.upload.assert_called_once()
        art.delete.assert_called_once_with("old-art")
        self.assertEqual(module.load_state()["content_id"], "new-art")

    def test_failed_selection_is_tracked_and_retried(self):
        module, art = self.prepare_update()
        art.get_current.return_value = {
            "event": "current_artwork", "content_id": "old-art",
            "matte_id": "shadowbox_polar", "portrait_matte_id": "none",
        }
        art.select_image.side_effect = TimeoutError("lost acknowledgement")
        with self.assertRaises(TimeoutError):
            module.synchronize()
        art.delete.assert_not_called()
        art.select_image.side_effect = None
        module.synchronize()
        art.upload.assert_called_once()
        art.upload.assert_called_with(str(module.IMAGE_FILE), matte="shadowbox_polar",
                                      portrait_matte="none")
        art.get_current.assert_called_once()
        self.assertEqual(module.load_state()["content_id"], "new-art")

    def test_failed_staging_never_selects_or_deletes_previous_art(self):
        module, art = self.prepare_update()
        with patch.object(module, "save_state", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                module.synchronize()
        art.select_image.assert_not_called()
        art.delete.assert_called_once_with("new-art")
        self.assertEqual(module.load_state()["content_id"], "old-art")

    def test_pending_selection_waits_until_art_mode_is_on(self):
        module, art = self.prepare_update()
        module.save_state("revision-1", "old-art", pending_upload={
            "token": "revision-2", "content_id": "new-art",
        })
        art.get_artmode.return_value = "off"
        module.synchronize()
        art.select_image.assert_not_called()
        art.delete.assert_not_called()
        self.assertEqual(module.load_state()["pending_upload"]["content_id"], "new-art")

    def test_failed_cleanup_save_keeps_ids_for_next_run(self):
        module, art = self.prepare_update()
        module.save_state("revision-2", "new-art", ["old-art"])
        with patch.object(module, "save_state", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                module.synchronize()
        self.assertEqual(module.load_state()["pending_deletions"], ["old-art"])
        self.assertEqual(module.load_state()["content_id"], "new-art")
        module.synchronize()
        self.assertEqual(module.load_state()["pending_deletions"], [])
        art.upload.assert_not_called()

    def test_old_pending_deletions_survive_another_update(self):
        module, art = self.prepare_update()
        module.save_state("revision-1", "old-art", ["older-art"])
        art.delete.return_value = False
        module.synchronize()
        self.assertEqual(module.load_state()["pending_deletions"], ["older-art", "old-art"])
        self.assertEqual(module.load_state()["content_id"], "new-art")

    def check_deletion_retry(self, failure):
        module, art = self.prepare_update()
        art.delete.side_effect = [failure, True]
        module.synchronize()
        self.assertEqual(module.load_state().get("pending_deletions"), ["old-art"])
        module.synchronize()
        self.assertEqual(module.load_state()["pending_deletions"], [])
        self.assertEqual(art.delete.call_count, 2)
        art.upload.assert_called_once()

    def test_unconfirmed_deletion_is_retried_when_collage_is_unchanged(self):
        self.check_deletion_retry(False)

    def test_failed_deletion_is_retried_when_collage_is_unchanged(self):
        self.check_deletion_retry(TimeoutError("TV busy"))

    def test_state_is_committed_before_old_image_is_deleted(self):
        module, art = self.prepare_update()

        observed = []

        def delete(content_id):
            observed.append((content_id, module.load_state()))
            return True

        art.delete.side_effect = delete
        module.synchronize()
        self.assertEqual(len(observed), 1)
        content_id, state = observed[0]
        self.assertEqual(content_id, "old-art")
        self.assertEqual(state["content_id"], "new-art")
        self.assertIn("old-art", state["pending_deletions"])

    def test_cleanup_does_not_depend_on_rereading_the_committed_state(self):
        module, art = self.prepare_update()
        previous = module.load_state()
        with patch.object(module, "load_state", side_effect=[previous, {}]):
            module.synchronize()
        self.assertEqual(module.load_state()["content_id"], "new-art")
        self.assertEqual(module.load_state()["token"], "revision-2")

    def test_pairing_token_info_is_suppressed(self):
        self.load()
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger = logging.getLogger("samsungtvws.connection")
        logger.addHandler(handler)
        self.addCleanup(logger.removeHandler, handler)
        logger.info("New token %s", "fake-secret")
        self.assertNotIn("fake-secret", stream.getvalue())

    def test_json_size_limit(self):
        module = self.load()
        body = b'{"token":"' + b"x" * (1024 * 1024) + b'"}'
        with patch.object(module, "urlopen", return_value=io.BytesIO(body)):
            with self.assertRaisesRegex(ValueError, "limit"):
                module.fetch_json("http://example.test/state")

    def test_small_json_response(self):
        module = self.load()
        with patch.object(module, "urlopen", return_value=io.BytesIO(b'{"token":"v1"}')):
            self.assertEqual(module.fetch_json("http://example.test/state"), {"token": "v1"})

    def test_oversize_download_keeps_previous_file_and_removes_temp(self):
        module = self.load()
        destination = self.root / "image.png"
        destination.write_bytes(b"previous image")
        with patch.object(module, "MAX_IMAGE_BYTES", 8, create=True), \
                patch.object(module, "urlopen", return_value=io.BytesIO(b"123456789")):
            with self.assertRaisesRegex(ValueError, "limit"):
                module.download("http://example.test/image", destination)
        self.assertEqual(destination.read_bytes(), b"previous image")
        self.assertEqual(list(self.root.iterdir()), [destination])

    def test_download_at_limit_succeeds(self):
        module = self.load()
        destination = self.root / "image.png"
        with patch.object(module, "MAX_IMAGE_BYTES", 8, create=True), \
                patch.object(module, "urlopen", return_value=io.BytesIO(b"12345678")):
            module.download("http://example.test/image", destination)
        self.assertEqual(destination.read_bytes(), b"12345678")

    def test_interrupted_download_cleans_temp_and_preserves_previous_file(self):
        module = self.load()
        destination = self.root / "image.png"
        destination.write_bytes(b"previous image")

        class InterruptedResponse(io.BytesIO):
            def read(self, size=-1):
                if self.tell():
                    raise TimeoutError("connection stalled")
                return super().read(4)

        with patch.object(module, "urlopen", return_value=InterruptedResponse(b"12345678")):
            with self.assertRaises(TimeoutError):
                module.download("http://example.test/image", destination)
        self.assertEqual(destination.read_bytes(), b"previous image")
        self.assertEqual(list(self.root.iterdir()), [destination])


if __name__ == "__main__":
    unittest.main()
