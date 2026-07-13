# Changelog

## [Unreleased]

### Changed

- PyPI trove classifier updated from Alpha to Production/Stable.

## [0.1.9] - 2026-07-13

### Added

- Manifest kind ``python-version`` for Python files containing ``__version__ = "..."`` assignments.

### Changed

- Python version handler
- Lift myself

### Fixed

- Require Typer 0.16+ so ``--help`` works with Click 8.2 and newer (fixes ``Parameter.make_metavar()`` errors when another package upgrades Click).
- Changelog render no longer adds extra blank lines after the title when the only preamble content is the separator before the first release heading.

## [0.1.8] - 2026-06-01

### Added

- Manifest kind ``synology-info`` for Synology DSM ``INFO`` files; use ``[[version_files]]`` with ``kind = "synology-info"`` to bump alongside ``pyproject.toml``.

## [0.1.7] - 2026-05-23

### Changed

- Extend external dependency autoupdate and refine CLI flags

## [0.1.6] - 2026-05-20

### Changed

- Update dependent's version
- Support mixed language repos

## [0.1.5] - 2026-05-14

### Added

- `build` command
- `distlift deploy`: create and push the next CI marker tag ``{prefix}_{N}`` (default prefix ``deploy``); optional registry checks via ``deploy.verify_indexes`` / ``--verify-indexes`` (Python: ``pip``, JS: ``npm``).

### Changed

- Support --all-packages in simplified command

## [0.1.4] - 2026-05-13

### Changed

- Only include packages with changes in mono-repo when using the simple command

## [0.1.3] - 2026-05-13

### Added

- Commands to create and edit the repo config file.
- Simple packages list in monorepo config (path only, derive name).
- Bare ``distlift`` supports ``--major``, ``--minor``, ``--patch``, and ``--version`` / ``-v`` (use at most one; when none are given, behavior is unchanged and the release is a patch bump).
- ``distlift release monorepo`` supports the same bump and explicit version flags. ``--default-bump`` is used only when none of those flags are set. ``--version`` applies one next version to every package in that release; on an interactive terminal distlift asks for confirmation first.

### Changed

- How to deal with GPG signing when the tests run on a local computer.
- By default we now publish only packages with changes in a monorepo.
- Commands to create and edit the repo config file.
- Simple packages list in monorepo config (path only, derive name).

## [0.1.2] - 2026-05-13

### Added

- User hooks
- Change-log editor.
- Ability to create and edit user-level and system-level configuration files.

### Changed

- Change-log file.

## [0.1.1] - 2026-05-13

### Changed

- Publish on command without options
- Fix misunderstanding
- Add debug config, tasks
- Add documentation
- Added changelog support

[0.1.1]: https://github.com/pyl1b/distlift/compare/4cb9ee5108b97668875fd2cac9a297a1190f572c...v0.1.1
[0.1.2]: https://github.com/pyl1b/distlift/compare/v0.1.1...v0.1.2
[0.1.3]: https://github.com/pyl1b/distlift/compare/v0.1.2...v0.1.3
[0.1.4]: https://github.com/pyl1b/distlift/compare/v0.1.3...v0.1.4
[0.1.5]: https://github.com/pyl1b/distlift/compare/v0.1.4...v0.1.5
[0.1.6]: https://github.com/pyl1b/distlift/compare/v0.1.5...v0.1.6
[0.1.7]: https://github.com/pyl1b/distlift/compare/v0.1.6...v0.1.7
[0.1.8]: https://github.com/pyl1b/distlift/compare/v0.1.7...v0.1.8
[0.1.9]: https://github.com/pyl1b/distlift/compare/v0.1.8...v0.1.9
[unreleased]: https://github.com/pyl1b/distlift/compare/v0.1.9...HEAD
