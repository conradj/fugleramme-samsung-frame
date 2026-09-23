# Release checklist

1. Update `VERSION` to `MAJOR.MINOR.PATCH` and move user-visible changes from
   `## [Unreleased]` into a `## [MAJOR.MINOR.PATCH] - YYYY-MM-DD` heading dated
   for the release. Leave an empty `Unreleased` section.
2. Run `python3 -m unittest discover -s tests -v` and
   `python3 scripts/build-release.py`. Inspect
   `unzip -l dist/frame-sync-<version>.zip` and
   `cat dist/release-notes-<version>.md`. Extract the ZIP into a fresh folder
   and check that `sudo python3 setup.py` can run there on a Debian/Ubuntu
   systemd machine.
3. Review and commit the version, changelog, and related source changes. Tag the
   release commit with `git tag v<version>` and push that tag with
   `git push origin v<version>`. The workflow checks the tag, runs tests, builds
   the ZIP and creates the GitHub Release. Do not tag before review.
4. Verify the [release](https://github.com/conradj/fugleramme-samsung-frame/releases)
   has the changelog notes and only the intended ZIP asset. Download and inspect
   that asset, then test a fresh install and an update from it.

For rollback, reinstall the previous release ZIP by running its `setup.py`.
Keep `/etc/frame-sync.env` and `/var/lib/frame-sync` intact. Check state-file
compatibility before downgrading if a newer version changed its format.
