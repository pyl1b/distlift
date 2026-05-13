# distlift

Tool for publishing packages.

## Changelog automation

Releases can update a [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
file using conventional commits (enabled by default via `changelog.enabled`).
Use `distlift changelog preview --version X.Y.Z` to inspect the proposed entry,
`distlift changelog update` to write `CHANGELOG.md`, and `--no-changelog` on the
default `distlift` command to skip changelog planning for one run.
