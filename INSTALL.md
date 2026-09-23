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

Enter the TV address and Fugleramme URL, put the TV in Art Mode, accept its
permission prompt, and confirm the picture. Setup enables the fifteen-minute
timer after that confirmation.

To update, download a newer release ZIP, extract it into a **new** folder, and
run `sudo python3 setup.py` there. Keep `/etc/frame-sync.env` and
`/var/lib/frame-sync` intact; they contain your settings, pairing token, and
sync history. You may remove the old extracted folder after updating.

For manual installation and troubleshooting, see the
[online technical guide](https://github.com/conradj/fugleramme-samsung-frame/blob/main/docs/advanced.md).
