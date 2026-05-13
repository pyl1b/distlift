# distlift

Tool for publishing packages.

## Changelog automation

Releases can update a [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
file using conventional commits (enabled by default via `changelog.enabled`).
Use `distlift changelog preview --version X.Y.Z` to inspect the proposed entry,
`distlift changelog update` to write `CHANGELOG.md` (by default your `$GIT_EDITOR`
/ `$EDITOR` opens that entry first; use `--no-editor` to skip). Use `--no-changelog`
on the default `distlift` command to skip changelog planning for one run, and
`--no-changelog-editor` to skip only the editor step while still updating the file.
