#!/usr/bin/env python3
"""Guided installation on an existing Debian/Ubuntu systemd host."""

import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit


SOURCE = Path(__file__).resolve().parent
CONFIG = Path("/etc/frame-sync.env")
APP = Path("/opt/frame-sync")
STATE = Path("/var/lib/frame-sync")
UNITS = Path("/etc/systemd/system")
ADVANCED_GUIDE = "https://github.com/conradj/fugleramme-samsung-frame/blob/main/docs/advanced.md"


def run(*command):
    return subprocess.run([str(part) for part in command], check=True)


def preflight():
    if sys.platform != "linux":
        raise RuntimeError("Run setup on the Linux machine running Fugleramme.")
    if sys.version_info < (3, 10):
        raise RuntimeError("Python 3.10 or newer is required.")
    if os.geteuid() != 0:
        raise RuntimeError("Run setup with: sudo python3 setup.py")
    if not shutil.which("apt-get") or not Path("/run/systemd/system").is_dir():
        raise RuntimeError(f"Guided setup needs Debian/Ubuntu with systemd. See {ADVANCED_GUIDE}.")
    for name in ("frame-sync.py", "requirements.txt", "frame-sync.service", "frame-sync.timer"):
        if not (SOURCE / name).is_file():
            raise RuntimeError(f"Missing {name}; download the whole project before running setup.")


def configure():
    if CONFIG.exists():
        print(f"Reusing {CONFIG}, including your existing token and state paths.")
        return False
    while True:
        host = input("TV IP address or hostname: ").strip()
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.\-]*", host):
            break
        print("Enter an IPv4 address or hostname, such as 192.168.1.42 or frame.local.")
    while True:
        url = input("Fugleramme URL [http://127.0.0.1:8080]: ").strip() or "http://127.0.0.1:8080"
        try:
            parsed = urlsplit(url)
            valid = (parsed.scheme in {"http", "https"} and parsed.hostname
                     and not parsed.username and not parsed.password
                     and not parsed.query and not parsed.fragment
                     and not re.search(r"[\s\x00-\x1f\x7f\"'\\$`%]", url))
            parsed.port  # Validate the port, if supplied.
        except ValueError:
            valid = False
        if valid:
            break
        print("Enter a base HTTP URL, such as http://192.168.1.10:8080, without /state or /collage.png.")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=CONFIG.parent,
                                         prefix=".frame-sync-", delete=False) as output:
            temporary = Path(output.name)
            output.write(f"TV_HOST={host}\nFUGLERAMME_URL={url.rstrip('/')}\n"
                         f"FRAME_SYNC_STATE_DIR={STATE}\nTV_TOKEN_FILE={STATE / 'tv-token.txt'}\n")
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(CONFIG)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return True


def install():
    # Pause updates before replacing code. Allow an in-flight sync to finish.
    if (UNITS / "frame-sync.timer").exists():
        run("systemctl", "disable", "--now", "frame-sync.timer")
        for _ in range(310):
            result = subprocess.run(
                ["systemctl", "show", "frame-sync.service", "--property=ActiveState", "--value"],
                check=True, capture_output=True, text=True,
            )
            if result.stdout.strip() not in {"active", "activating", "deactivating", "reloading"}:
                break
            time.sleep(1)
        else:
            raise RuntimeError("The previous sync is still running. Wait for it to finish and rerun setup.")
    print("Installing dependencies and the automatic update service…")
    run("apt-get", "update")
    run("apt-get", "install", "-y", "python3", "python3-venv")
    try:
        pwd.getpwnam("frame-sync")
    except KeyError:
        run("useradd", "--system", "--user-group", "--home-dir", STATE,
            "--shell", "/usr/sbin/nologin", "frame-sync")
    run("install", "-d", "-m", "755", APP)
    run("install", "-d", "-o", "frame-sync", "-g", "frame-sync", "-m", "700", STATE)
    run("install", "-m", "644", SOURCE / "frame-sync.py", SOURCE / "requirements.txt", APP)
    run("python3", "-m", "venv", APP / ".venv")
    run(APP / ".venv/bin/python", "-m", "pip", "install", "-r", APP / "requirements.txt")
    run("install", "-m", "644", SOURCE / "frame-sync.service", SOURCE / "frame-sync.timer", UNITS)
    run("systemctl", "daemon-reload")


def reuse_token():
    destination = STATE / "tv-token.txt"
    if destination.exists():
        print("Keeping the saved TV pairing token.")
        return
    while True:
        answer = input("Existing TV token file to reuse [Enter to pair with the TV]: ").strip()
        if not answer:
            return
        source = Path(answer).expanduser()
        if source.is_file() and source.stat().st_size:
            run("install", "-o", "frame-sync", "-g", "frame-sync", "-m", "600", source, destination)
            return
        print("That file is missing or empty. Enter its full path, or press Enter to pair.")


def pair_and_test():
    print("\nPut the TV in Art Mode. Accept any FrameSync permission prompt on the TV.")
    print("If pairing times out, accept the prompt and try again here.")
    while True:
        if input("Press Enter to send the collage, or q to finish later: ").strip().lower() == "q":
            print("Automatic updates are off. Rerun setup when you are ready.")
            return False
        succeeded = True
        try:
            run("systemctl", "start", "frame-sync.service")
        except subprocess.CalledProcessError:
            succeeded = False
            print("The sync failed. Check the log below and the TV permission prompt.")
        run("journalctl", "-u", "frame-sync.service", "-n", "15", "--no-pager")
        if succeeded and input("Is the Fugleramme collage showing on the TV? [y/N]: ").strip().lower() in {"y", "yes"}:
            run("systemctl", "enable", "--now", "frame-sync.timer")
            print("\nSetup complete. New collages will be checked every 15 minutes while the TV is in Art Mode.")
            return True
        print("Check the TV is in Art Mode and the addresses in /etc/frame-sync.env are correct.")
        print(f"For more help, see {ADVANCED_GUIDE}. You can retry or finish later.")


def main():
    preflight()
    print("Fugleramme → Samsung Frame setup\n")
    new_config = configure()
    install()
    if new_config:
        reuse_token()
    return 0 if pair_and_test() else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        print("\nSetup interrupted. Rerun sudo python3 setup.py to continue.")
        sys.exit(1)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f"\nSetup stopped: {error}\nFix the problem and rerun sudo python3 setup.py.", file=sys.stderr)
        sys.exit(1)
