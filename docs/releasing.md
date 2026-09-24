# Releases

Every pull request merged into `main` starts **Release merged PR**. By default,
it advances the patch number in `VERSION` and adds a dated `CHANGELOG.md` entry
from the PR title and number. It then runs the offline tests, builds the
installer ZIP, commits the version and notes to `main`, tags that commit, and
publishes a GitHub Release with the ZIP and matching notes. A rerun recognizes
a PR that already has an entry and uses its existing version.

For an intentional minor or major release, open the PR first to get its number.
Before merging, commit the intended `VERSION` and a dated changelog section for
that version to the PR branch. Include the PR number once in a bullet, as
`(#<number>)`. The release workflow recognizes that entry and publishes the
version already committed by the PR instead of advancing the patch number.
Keep the `Unreleased` section empty.

Write a user-facing PR title: it becomes the release note. Put detailed changes
in the PR description for reviewers. Check the workflow run after merging. A
failed run can be rerun after fixing its cause.

The [v0.1.0](https://github.com/conradj/fugleramme-samsung-frame/releases/tag/v0.1.0)
and [v0.1.1](https://github.com/conradj/fugleramme-samsung-frame/releases/tag/v0.1.1)
installer releases were published from their historical merge commits. Each
contains the installer ZIP and notes from its `CHANGELOG.md` section.

The tag-push workflow remains available for an intentional release outside the
PR merge flow. Before manually tagging, update `VERSION` and `CHANGELOG.md`, run
`python3 -m unittest discover -s tests -v` and
`python3 scripts/build-release.py`, and review the ZIP and notes in `dist/`.
Push `v<version>` only after reviewing the release commit.

For rollback, reinstall the previous release ZIP by running its `setup.py`.
Keep `/etc/frame-sync.env` and `/var/lib/frame-sync` intact. Check state-file
compatibility before downgrading if a newer version changed its format.
