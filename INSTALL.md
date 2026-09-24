# Install Frame Sync

Use a Debian or Ubuntu machine with systemd, Python 3.10 or newer, sudo access,
and network access to your Fugleramme server and Samsung Frame TV. Fugleramme
must already be running. Run this on its host machine if Fugleramme uses Docker.

Download the `frame-sync-<version>.zip` asset from the
[latest release](https://github.com/conradj/fugleramme-samsung-frame/releases/latest),
then run (replace `<version>` with the archive's version):

```bash
unzip frame-sync-<version>.zip
cd frame-sync-<version>
sudo python3 setup.py
```

Enter the TV address, put the TV in Art Mode, accept a permission prompt if
one appears, and confirm the picture. On later runs, press Enter to keep the
saved TV address. Setup uses Fugleramme at `http://127.0.0.1:8080` by default;
if it runs elsewhere, edit `FUGLERAMME_URL` in `/etc/frame-sync.env` before
pressing Enter to send the collage. Setup enables the fifteen-minute timer
after confirmation.

To update, download a newer release ZIP, extract it into a **new** folder, and
run `sudo python3 setup.py` there. Keep `/etc/frame-sync.env` and
`/var/lib/frame-sync` intact; they contain your settings, pairing token, and
sync history. You may remove the old extracted folder after updating.

For manual installation and troubleshooting, see the
[online technical guide](https://github.com/conradj/fugleramme-samsung-frame/blob/main/docs/advanced.md).
