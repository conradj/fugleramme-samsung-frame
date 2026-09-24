#!/usr/bin/env python3
"""Synchronize a Fugleramme collage to a Samsung Frame while Art Mode is on."""

from __future__ import annotations

import fcntl
import json
import logging
import os
from pathlib import Path
import tempfile
import time
from typing import Any
from urllib.request import urlopen

from samsungtvws import SamsungTVWS, exceptions
from websocket import WebSocketException


TV_HOST = os.environ.get("TV_HOST", "").strip()
FUGLERAMME_URL = os.environ.get("FUGLERAMME_URL", "http://127.0.0.1:8080").rstrip("/")
STATE_DIR = Path(os.environ.get(
    "FRAME_SYNC_STATE_DIR", str(Path.home() / ".local/state/frame-sync")
)).expanduser()
TOKEN_FILE = Path(os.environ.get("TV_TOKEN_FILE", str(STATE_DIR / "tv-token.txt"))).expanduser()
RETRIES = int(os.environ.get("FRAME_SYNC_RETRIES", "3"))
MAX_JSON_BYTES = 1024 * 1024
MAX_IMAGE_BYTES = 32 * 1024 * 1024

STATE_FILE = STATE_DIR / "state.json"
IMAGE_FILE = STATE_DIR / "collage.png"
LOCK_FILE = STATE_DIR / "lock"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
# samsungtvws logs pairing tokens at INFO, including during normal pairing.
logging.getLogger("samsungtvws").setLevel(logging.WARNING)
LOG = logging.getLogger("frame-sync")


def fetch_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=20) as response:  # noqa: S310 - trusted LAN URL
        body = response.read(MAX_JSON_BYTES + 1)
    if len(body) > MAX_JSON_BYTES:
        raise ValueError("JSON response exceeds size limit")
    value = json.loads(body)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def download(url: str, destination: Path) -> None:
    temporary = None
    try:
        with urlopen(url, timeout=60) as response:  # noqa: S310 - trusted LAN URL
            with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as output:
                temporary = Path(output.name)
                size = 0
                while chunk := response.read(min(64 * 1024, MAX_IMAGE_BYTES - size + 1)):
                    size += len(chunk)
                    if size > MAX_IMAGE_BYTES:
                        raise ValueError("Image response exceeds size limit")
                    output.write(chunk)
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_state() -> dict[str, Any]:
    try:
        value = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_state(
    token: str,
    content_id: str,
    pending_deletions: list[str] | None = None,
    pending_upload: dict[str, str] | None = None,
) -> None:
    data = {
        "token": token,
        "content_id": content_id,
        "updated_at": int(time.time()),
        "pending_deletions": pending_deletions or [],
        "pending_upload": pending_upload,
    }
    temporary = STATE_FILE.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        output.write(json.dumps(data, indent=2) + "\n")
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(STATE_FILE)


def open_art_if_active():
    """Return an open Art API connection only when the TV reports Art Mode on."""
    for attempt in range(1, RETRIES + 1):
        art = None
        try:
            tv = SamsungTVWS(
                host=TV_HOST,
                port=8002,
                token_file=str(TOKEN_FILE),
                timeout=15,
                name="FrameSync",
            )
            art = tv.art()
            mode = str(art.get_artmode()).strip().lower()
            if mode in {"on", "true", "1"}:
                return art
            art.close()
            LOG.info("TV is not in Art Mode; leaving the collage pending")
            return None
        except Exception as error:  # Samsung's event ordering can be intermittent
            if art is not None:
                try:
                    art.close()
                except Exception:
                    pass
            if attempt == RETRIES:
                LOG.warning("Could not read Art Mode after %d attempts: %s", RETRIES, error)
                return None
            time.sleep(2)
    return None


def matte_for_upload(art, managed_content_id: str) -> tuple[str, str]:
    """Copy matte only from the currently displayed artwork we own."""
    if not managed_content_id:
        return "none", "none"

    for attempt in range(2):
        try:
            current = art.get_current()
            break
        except (exceptions.ConnectionFailure, exceptions.ResponseError,
                WebSocketException, OSError):
            if attempt:
                LOG.warning("Could not read the managed artwork's matte; uploading without a matte")
                return "none", "none"

    if not isinstance(current, dict):
        LOG.warning("Current artwork metadata is incomplete; uploading without a matte")
        return "none", "none"
    if current.get("content_id") != managed_content_id:
        LOG.info("Current TV artwork differs from the managed collage; uploading without a matte")
        return "none", "none"

    matte = current.get("matte_id")
    portrait_matte = current.get("portrait_matte_id")
    if (not isinstance(matte, str) or not matte.strip()
            or not isinstance(portrait_matte, str) or not portrait_matte.strip()):
        LOG.warning("Managed artwork matte metadata is incomplete; uploading without a matte")
        return "none", "none"
    return matte, portrait_matte


def synchronize() -> None:
    if not TV_HOST:
        raise ValueError("TV_HOST is required; set it to your TV's IP address or hostname")
    if RETRIES < 1:
        raise ValueError("FRAME_SYNC_RETRIES must be at least 1")
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)

    with LOCK_FILE.open("w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            LOG.info("Another synchronization is already running")
            return

        fugleramme_state = fetch_json(f"{FUGLERAMME_URL}/state")
        token = str(fugleramme_state.get("token", "")).strip()
        if not token:
            raise RuntimeError("Fugleramme returned no state token")

        previous = load_state()
        pending_upload = previous.get("pending_upload")
        pending_deletions = previous.get("pending_deletions", [])
        if token == previous.get("token") and not pending_upload and not pending_deletions:
            LOG.info("Collage is unchanged")
            return

        art = open_art_if_active()
        if art is None:
            return

        try:
            if not pending_upload and token != previous.get("token"):
                download(f"{FUGLERAMME_URL}/collage.png?v={token}", IMAGE_FILE)
                matte, portrait_matte = matte_for_upload(art, previous.get("content_id", ""))
                new_content_id = art.upload(str(IMAGE_FILE), matte=matte,
                                            portrait_matte=portrait_matte)
                pending_upload = {"token": token, "content_id": new_content_id}
                try:
                    # Record the upload before selection: a lost acknowledgement or
                    # failed commit can then be retried without uploading again.
                    save_state(previous.get("token", ""), previous.get("content_id", ""),
                               pending_deletions, pending_upload)
                except Exception:
                    # Selection has not been attempted, so this upload is safe to
                    # remove. Never roll back an image after attempting selection.
                    try:
                        if not art.delete(new_content_id):
                            LOG.warning("Could not remove unrecorded upload %s", new_content_id)
                    except Exception:
                        LOG.warning("Could not remove unrecorded upload %s", new_content_id)
                    raise

            if pending_upload:
                new_content_id = pending_upload["content_id"]
                art.select_image(new_content_id, show=True)
                old_content_id = previous.get("content_id", "")
                if old_content_id and old_content_id != new_content_id:
                    pending_deletions = list(dict.fromkeys([*pending_deletions, old_content_id]))
                pending_deletions = [cid for cid in pending_deletions if cid != new_content_id]
                save_state(pending_upload["token"], new_content_id, pending_deletions)
                previous = {"token": pending_upload["token"], "content_id": new_content_id}
                LOG.info("Displayed collage %s", new_content_id)

            remaining = []
            for content_id in pending_deletions:
                if content_id == previous.get("content_id"):
                    continue
                try:
                    deleted = art.delete(content_id)
                except Exception:
                    deleted = False
                if not deleted:
                    remaining.append(content_id)
                    LOG.warning("Deletion remains pending for %s", content_id)
            if remaining != pending_deletions:
                save_state(previous.get("token", ""), previous.get("content_id", ""), remaining)
        finally:
            art.close()


if __name__ == "__main__":
    os.umask(0o077)
    try:
        synchronize()
    except Exception:
        LOG.exception("Synchronization failed")
        raise SystemExit(1)
