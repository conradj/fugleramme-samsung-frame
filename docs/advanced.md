# Technical guide and manual installation

For the guided setup, start with the [README](../README.md).
This guide covers the sync behaviour, manual installation, custom settings and troubleshooting.
Run commands from the downloaded project directory, not from this docs directory.

## How synchronization works

Install this Python service on the **same VM or Linux machine that already runs
Fugleramme** to send updated collages to a Samsung Frame TV. **No additional VM
is required.** The instructions below assume this shared-machine setup.

A systemd timer checks every 15 minutes. It uploads only when
Fugleramme's state token changes and the TV reports that Art Mode is already on.
It sends no power or Art Mode toggle commands.

After selecting a new collage, it saves the new state before deleting preceding
Samsung content IDs recorded by this service. Failed deletions stay queued and
are retried on later runs, including when the collage is unchanged. It does not
enumerate or bulk-delete other artwork.
If the TV is unavailable or not in Art Mode, the change stays pending. Changing
Fugleramme's layout settings also changes its state token.

Uploads are recorded before selection. If selection or the subsequent state save
fails, the next run resumes the recorded upload while Art Mode is on. Existing
state files are accepted without manual migration. An interruption before the TV
returns an upload ID or before that ID can be saved can still leave an untracked
upload; the service does not search for or delete unknown artwork.

HTTP responses are limited to 1 MiB for state JSON and 32 MiB for an image.
Images are downloaded in chunks, and failed downloads preserve the previous
local image. The systemd service has a five-minute runtime limit so a stalled
connection cannot block later timer runs indefinitely.


## Requirements

- Your existing Fugleramme VM or Linux machine, with systemd, Python 3.10 or
  newer, and sudo access. The commands below target Debian/Ubuntu; use equivalent
  packages on other distributions.
- Fugleramme already running, with `/state` returning JSON containing a nonempty
  `token`, and `/collage.png` serving the collage. This project does not install
  Fugleramme itself.
- A Samsung Frame with a compatible Art API. Compatibility depends on model and
  firmware; the Python client is [samsungtvws](https://github.com/xchwarze/samsung-tv-ws-api).
- Network access from this machine to Fugleramme and the TV, including the TV's secure
  WebSocket port 8002 and its negotiated image-transfer port. Use a trusted network.

## 1. Download and install

For guided setup, download the `frame-sync-<version>.zip` asset from the
[latest release](https://github.com/conradj/fugleramme-samsung-frame/releases/latest),
extract it, enter the `frame-sync-<version>` directory and run
`sudo python3 setup.py`. GitHub's automatically generated source ZIP is a
different download. It contains the development repository, including photos
and tests. You can also clone the repository for development.

The manual steps below work from either the release ZIP or a source checkout:
both include the runtime script, requirements, example configuration and
systemd units. Run commands from the directory containing those files.

Install the prerequisites and create a dedicated account:

```bash
sudo apt update
sudo apt install -y python3 python3-venv
python3 --version
sudo useradd --system --user-group --home-dir /var/lib/frame-sync --shell /usr/sbin/nologin frame-sync
```

If the account already exists, skip `useradd`. Install the code and dependencies:

```bash
sudo install -d -m 755 /opt/frame-sync
sudo install -d -o frame-sync -g frame-sync -m 700 /var/lib/frame-sync
sudo install -m 644 frame-sync.py requirements.txt /opt/frame-sync/
sudo python3 -m venv /opt/frame-sync/.venv
sudo /opt/frame-sync/.venv/bin/python -m pip install -r /opt/frame-sync/requirements.txt
```

The requirements include `samsungtvws[cli]`, which installs both the Python
library and the `samsungtv` command used below. If you installed an earlier
version of this project, copy the updated `requirements.txt` and rerun the pip
command to add the CLI.

Fugleramme itself does not require a VM: its
[upstream instructions](https://github.com/arnegiacomo/fugleramme#readme) also cover
installation on a Raspberry Pi and running in Docker, including web-only use
without an e-ink display. This synchronizer only needs its HTTP endpoints.

Install this service in the VM's or Linux machine's operating system. If
Fugleramme runs in Docker on that same machine, publish its HTTP port and use
`http://127.0.0.1:8080` (or your chosen published port). You can optionally run
the synchronizer on another Linux machine; in that case, set `FUGLERAMME_URL`
to Fugleramme's network address instead of `127.0.0.1`.

## 2. Configure your setup

```bash
sudo install -o root -g root -m 600 frame-sync.env.example /etc/frame-sync.env
sudoedit /etc/frame-sync.env
```

Set `TV_HOST` to your TV's actual IP address or hostname. The example intentionally
leaves it blank; the service refuses to run until it is set. Reserving the TV's
address in your router avoids changes after a reboot.

Set `FUGLERAMME_URL` to the address reachable from the VM. The example
`http://127.0.0.1:8080` assumes Fugleramme is on the same VM and port 8080; replace
it if your setup differs. Use the base URL without `/state` or `/collage.png`.

| Setting | Purpose | Default for direct script execution |
| --- | --- | --- |
| `TV_HOST` | TV IP address or hostname, without scheme or port | Required |
| `FUGLERAMME_URL` | Fugleramme base URL | `http://127.0.0.1:8080` |
| `FRAME_SYNC_STATE_DIR` | Directory for state, image, and lock | `~/.local/state/frame-sync` |
| `TV_TOKEN_FILE` | Samsung pairing token file | `tv-token.txt` inside the state directory |
| `FRAME_SYNC_RETRIES` | Attempts to read Art Mode per run | `3`; positive integer |

The supplied service and example use `/var/lib/frame-sync` for state and the
token. Use simple `KEY=value` assignments and absolute paths in the config, with
no `export`, `$HOME`, or shell commands. If you choose custom paths, create them
and make them writable by the `frame-sync` account.

## 3. Pair and test

Manually turn the TV on. First check whether it advertises Art Mode support.
This command reads your settings from `/etc/frame-sync.env` and runs the CLI as
the same account used by the service:

```bash
sudo bash -c '
set -eu
. /etc/frame-sync.env
umask 077
exec sudo -u frame-sync /opt/frame-sync/.venv/bin/samsungtv \
  --host "$TV_HOST" \
  --port 8002 \
  --token-file "$TV_TOKEN_FILE" \
  --name FrameSync \
  art-supported
'
```

Expect `True`. This checks the TV's reported capability; it does not prove that
pairing or image upload works. Accept any **FrameSync** connection prompt on the
TV. Then, while the television is showing your collage or another artwork in
Art Mode, run:

```bash
sudo bash -c '
set -eu
. /etc/frame-sync.env
umask 077
exec sudo -u frame-sync /opt/frame-sync/.venv/bin/samsungtv \
  --host "$TV_HOST" \
  --port 8002 \
  --token-file "$TV_TOKEN_FILE" \
  --name FrameSync \
  art-mode
'
```

Accept any further **FrameSync** connection prompt. Expect `on` while the TV is
in Art Mode. This command reads the current mode without changing it or uploading
an image, and saves a token when the TV supplies one. If permission times out,
accept the prompt and rerun the command. These commands are documented in the
[upstream CLI source](https://github.com/xchwarze/samsung-tv-ws-api/blob/master/samsungtvws/cli/art.py).

Install the systemd units:

```bash
sudo install -m 644 frame-sync.service frame-sync.timer /etc/systemd/system/
sudo systemctl daemon-reload
```

Manually turn the TV on and put it in Art Mode. Start one synchronization while
watching the TV, and accept the connection permission prompt for **FrameSync**
if it appears:

```bash
sudo systemctl start frame-sync.service
sudo journalctl -u frame-sync.service -n 50 --no-pager
```

The client saves the pairing token at `TV_TOKEN_FILE` when the TV supplies it.
If the prompt times out, accept permission and run the service again. TV settings
may require allowing remote connections or removing a previously denied client.
Pairing uses the library's
[token-file support](https://github.com/xchwarze/samsung-tv-ws-api/blob/master/samsungtvws/connection.py).

If you already have a working token, you can copy it instead. Replace the source
path below with your token file and adjust the destination if configured:

```bash
sudo install -o frame-sync -g frame-sync -m 600 /path/to/existing-token.txt /var/lib/frame-sync/tv-token.txt
```

Confirm that the log says `Displayed collage` and the collage appears on the TV.
A successful systemd exit alone is insufficient: the script also exits normally
when it skips an unchanged collage or cannot read active Art Mode.

## 4. Enable automatic checks

Once the manual test works:

```bash
sudo systemctl enable --now frame-sync.timer
systemctl list-timers frame-sync.timer
```

The timer runs about two minutes after boot and every 15 minutes thereafter.
If Fugleramme has not started yet, a failed request is retried on the next run.

To change the interval, run `sudo systemctl edit frame-sync.timer` and enter:

```ini
[Timer]
OnUnitActiveSec=
OnUnitActiveSec=5min
```

Then apply it:

```bash
sudo systemctl daemon-reload
sudo systemctl restart frame-sync.timer
```

## Operation and troubleshooting

```bash
# Run immediately; settings are read again on every service start.
sudo systemctl start frame-sync.service

# Read recent logs.
sudo journalctl -u frame-sync.service -n 50 --no-pager

# Stop automatic checks.
sudo systemctl disable --now frame-sync.timer
```

- **Missing `TV_HOST`:** fill in `/etc/frame-sync.env`.
- **HTTP errors or no state token:** check the Fugleramme URL, published Docker
  port, and that your Fugleramme version provides the endpoints listed above.
- **Could not read Art Mode:** check the TV address, routing/firewall, pairing
  permission, and Art API compatibility. A powered-off TV is an expected skip.
- **Permission denied:** ensure custom state/token paths belong to `frame-sync`.
- **Collage is unchanged:** change Fugleramme content or layout to produce a new
  state token if you want to test another upload.
- **Response exceeds size limit:** check that the URL serves the expected JSON
  or PNG. State JSON must be at most 1 MiB and collages at most 32 MiB.
- **Deletion remains pending:** the old content ID stays in `state.json` for a
  later cleanup attempt. Cleanup runs only while Art Mode is on. If an ID was
  already deleted but the TV never confirms it, it can remain queued.
- **Service timed out:** systemd stops runs after five minutes. Check connectivity
  and TV responsiveness; the timer will try again on its next scheduled run.

Keep `state.json` when updating: it tracks the last uploaded artwork. Removing it
loses that reference and can leave the old upload on the TV. When changing to a
different TV or Fugleramme instance, use a separate state directory and token
file so content IDs are not reused across devices.

For a guided update, extract a newer release ZIP into a fresh directory and
rerun `sudo python3 setup.py` there. It pauses the timer, waits for a running
sync, and keeps `/etc/frame-sync.env` and `/var/lib/frame-sync` intact. For a
manual update, stop the timer, wait for any running service to finish, download
the new files, and repeat the code/dependency and unit installation commands.
Keep those same configuration and state paths, reload systemd, test once, and
enable the timer again.

## Run without systemd

For a single run as your own Linux user, from the downloaded directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
TV_HOST=your-tv-hostname FUGLERAMME_URL=http://127.0.0.1:8080 .venv/bin/python frame-sync.py
```

Replace the hostname and URL with your setup. The script reads environment
variables; it does not automatically load `/etc/frame-sync.env` or a `.env` file.
Manual runs use your user's state directory unless overridden, so do not mix
them with the system service for the same TV. Use `systemctl start` to test an
installed service with the same account, token, and state.

The five-minute limit is enforced by systemd; direct script runs retain only
the individual socket timeouts.

## Development and sharing

Run the offline tests without a TV or installed dependencies:

```bash
python3 -m unittest discover -s tests -v
```

Publish the source and `frame-sync.env.example`. Keep your filled-in configuration,
pairing tokens, downloaded collages, virtual environment, and runtime state private.
The included `.gitignore` excludes their conventional local filenames; custom
filenames need equivalent exclusions. The synchronizer suppresses the client
library's INFO messages, which include newly issued pairing tokens. Check logs
before sharing them: CLI commands and error diagnostics can still include
sensitive device details.
