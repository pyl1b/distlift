# distlift — Agent Guide

## Changelog

Log changes only for **production code** edits (not tests). Before finishing a
task that changed application or library source, update the nearest
`CHANGELOG.md` (walk up from edited paths). If none exists, create one at the
repository root with `## [Unreleased]` and Added/Changed/Fixed sections. Add at
least one bullet describing what changed for users.

**Do not** update the changelog when: the task was read-only; you are in **Plan
mode** or only writing/updating plans (including `.cursor/plans/`); changes are
**tests only** (`tests/`, `*_test.py`, test fixtures); or the user asked not to
update it.

## What this project is

`distlift` is a Python library and CLI tool that automates version bumping, Git
tagging, and release orchestration for Python and JavaScript packages. It
supports single-package repositories and monorepos where each package is
versioned independently.

The installed console script is `distlift`. The same entry point is exposed as
`python -m distlift`.

---

## Quick orientation

```
src/distlift/
  __init__.py          package version metadata
  __main__.py          python -m distlift entry point
  app.py               DistliftApplication — orchestration boundary between CLI and core
  cli.py               typer CLI (release, build, changelog, config, plugins)
  cli_changelog.py     ``distlift changelog`` Typer subcommands
  constants.py         ENV_PREFIX, default paths, tag templates, entry-point group name
  errors.py            typed exception hierarchy
  logging_utils.py     configure_logging(), get_logger(), TRACE level (5)

  plugins/
    base.py            abstract plugin interfaces (DistliftPlugin and six capability subclasses)
    registry.py        PluginRegistry — holds active implementations, enforces override rules
    discovery.py       discover plugins from entry points, explicit paths, and directories
    loader.py          import plugin modules and instantiate plugin objects
    manager.py         PluginManager — coordinates discovery → loading → registry creation
    builtins.py        build_builtin_plugins() — wires built-in implementations
    scaffold.py        create_dependency_updater_plugin() plugin project template

  dependencies/
    models.py          ReleasedProjectVersion, DependencyUpdateRequest/Result
    projects.py        project lists, PEP 503 name normalization, enablement filters
    python.py          pyproject.toml dependency find/update (packaging + tomlkit)
    javascript.py      package.json dependency find/update
    service.py         run_builtin_dependency_updates(), rule and scan orchestration
    configured_plugin.py ConfiguredDependencyUpdaterPlugin (TOML rules)
    format.py          CLI autoupdate summary lines

  changelog/
    builder.py         assemble changelog update plans from Git history and settings
    compare_url.py     derive compare URL templates from ``git remote`` URLs
    conventional.py    conventional-commit parsing for changelog routing
    editor_prompt.py   optional external-editor session for release fragments
    formatter.py       render structured changelog models as Markdown
    git_log.py         collect commits between revisions for changelog builds
    models.py          changelog document structures and update plans
    parser.py          parse Keep-a-Changelog Markdown into models
    plugin.py          KeepAChangelogBuiltinPlugin registration hook
    writer.py          persist formatted changelog documents

  config/
    models.py          enums … RawConfig (with ``changelog_overlay``), ResolvedConfig,
                       PluginConfig, ``ChangelogConfig``, …
    discovery.py       locate config files on disk (local, user, system, pyproject embed)
    loader.py          load TOML files and env vars into RawConfig fragments
    merger.py          merge ordered RawConfig layers into ResolvedConfig with source tracing
    validators.py      semantic validation of ResolvedConfig after merge

  versioning/
    models.py          VersionParts, VersionSelection, ResolvedVersion (all frozen attrs)
    parser.py          parse_version(), parse_tag_version(), strip_tag_prefix()
    formatter.py       format_version(), format_tag()
    bump.py            bump_version(), validate_bump_allowed(), coerce_initial_version()
    resolver.py        resolve_current_version(), resolve_next_version(), find_latest_matching_tag()

  vcs/
    git.py             GitRepository (subprocess wrapper) + GitBackendBuiltinPlugin
    tags.py            build_tag_pattern(), sort_tags_by_version(), find_latest_tag_for_package()

  languages/
    base.py            ProjectAdapter ABC
    python.py          PythonProjectAdapter + PythonProjectPlugin
    javascript.py      JavaScriptProjectAdapter + JavaScriptProjectPlugin

  manifests/
    pyproject_file.py  read/write pyproject.toml via tomlkit (format-preserving)
    package_json_file.py read/write package.json via stdlib json

  release/
    models.py          ReleaseTarget, SimpleReleaseRequest, MonorepoReleaseRequest,
                       PackageReleasePlan, ReleasePlan, ReleaseResult
    planner.py         build pure ReleasePlan without side effects
    simple.py          compute_simple_release_plan()
    monorepo.py        compute_monorepo_release_plan()
    changelog_extra.py finalize_plan_with_changelog() attaches per-package changelog plans
    executor.py        ReleaseExecutor — changelogs, manifests, dependency updates, commit, tags

  monorepo/
    discovery.py       load_managed_packages(), resolve_package_manifest_path()
    change_detector.py find_changed_packages() via git diff per package path

  publish/
    models.py          BuildArtifact, PublishRequest, PublishResult
    python.py          build_python_distributions(), publish_python_distributions()
    javascript.py      build_javascript_distributions(), publish_javascript_distributions()

tests/                 mirrors src/ structure; includes ``tests/changelog/``,
                       ``tests/dependencies/``
```

---

## Technology choices

| Concern | Choice |
|---|---|
| Build backend | hatchling |
| CLI framework | typer |
| Structured models | attrs (`@attrs.define`, `@attrs.define(frozen=True)`) |
| TOML read-only | stdlib `tomllib` (Python ≥ 3.11) |
| TOML read/write (format-preserving) | `tomlkit` |
| Enums | `StrEnum` (Python ≥ 3.11) |
| Git integration | subprocess wrappers — no Git Python binding |
| Plugin discovery | Python entry-point group `distlift.plugins` + filesystem paths |
| Testing | pytest |
| Lint / format | ruff |
| Type checking | mypy (dev only) |

Target Python versions: 3.11, 3.12, 3.13.

---

## Configuration system

Precedence, highest to lowest:

1. CLI flags (applied in `_resolve_app_config` inside `cli.py`)
2. Environment variables (`DISTLIFT_*`)
3. Local repo config (`distlift.toml`, `.distlift.toml`, `[tool.distlift]` in `pyproject.toml`)
4. User config (`%APPDATA%/distlift/config.toml` on Windows; `~/.config/distlift/config.toml` elsewhere)
5. System config (`%ProgramData%/distlift/config.toml` on Windows; `/etc/distlift/config.toml` elsewhere)
6. Built-in defaults (in `constants.py` and `config/models.py`)

Each layer is loaded as a `RawConfig` by `config/loader.py`. All layers are
merged by `config/merger.py` into one `ResolvedConfig`. Field sources are
tracked in `ResolvedConfig.field_sources` for the `config show` command.

Key environment variables: `DISTLIFT_LANGUAGE`, `DISTLIFT_MODE`,
`DISTLIFT_REMOTES`, `DISTLIFT_DEFAULT_VERSION`, `DISTLIFT_VERSION_FORMAT`,
`DISTLIFT_TAG_TEMPLATE`, `DISTLIFT_VERSION_SOURCE`, `DISTLIFT_MANIFEST_PATH`,
`DISTLIFT_EDITOR`, `DISTLIFT_PLUGIN_PATHS`, `DISTLIFT_PLUGIN_DIRS`,
`DISTLIFT_ENABLE_ENVIRONMENT_PLUGINS`, `DISTLIFT_ENABLE_BUILTIN_PLUGINS`,
`DISTLIFT_CHANGELOG_ENABLED`, `DISTLIFT_CHANGELOG_PATH`,
`DISTLIFT_CHANGELOG_COMPARE_URL_TEMPLATE`, `DISTLIFT_CHANGELOG_TITLE`,
`DISTLIFT_CHANGELOG_PROMPT_EDITOR`, `DISTLIFT_DEPLOY_TAG_PREFIX`,
`DISTLIFT_DEPLOY_VERIFY_INDEXES`.

When `changelog.prompt_editor` is true (default), non–dry-run releases and
`distlift changelog update` open an editor on the generated release fragment
before writing. The editor is resolved in this order: `$GIT_EDITOR`, then
`$VISUAL`, then `$EDITOR`, then the top-level `editor` setting in distlift
config (TOML key `editor` or `DISTLIFT_EDITOR`). The same lookup chain is
used by `distlift config edit-user` and `distlift config edit-system`.
If `stdin` is not a TTY (typical CI), the generated changelog entry is kept
without prompting. Disable per run with `--no-changelog-editor` /
`--no-editor`, or set `changelog.prompt_editor = false` /
`DISTLIFT_CHANGELOG_PROMPT_EDITOR=false`.

Key dependency-update environment variables:
`DISTLIFT_DEPENDENCY_UPDATES_ENABLED`,
`DISTLIFT_DEPENDENCY_UPDATES_INCLUDE_CURRENT_MONOREPO`.
Hook event `dependencies_autoupdated` exposes `DISTLIFT_DEPENDENCY_UPDATE_*`
summary variables after dependency files are written.

---

## Plugin system

Plugin load order (later overrides earlier when `allow_override` is true):

1. Built-in plugins (`plugins/builtins.py`)
2. Environment-discovered plugins (entry-point group `distlift.plugins`)
3. Explicit plugin file/package paths (CLI `--plugin` or config `plugins.paths`)
4. Plugins found in explicit directories (CLI `--plugin-dir` or config `plugins.directories`)

A filesystem plugin module must export either a callable `get_plugin()` that
returns a `DistliftPlugin` instance, or a class named `Plugin` (or
`<ModuleName>Plugin`) that subclasses `DistliftPlugin`.

`PluginRegistry` stores one active implementation per capability key (language
name, manifest kind, etc.). Registering a duplicate key raises `PluginError`
unless `allow_override` is `True`.

---

## Release flow

### Simple mode

```
app.run_simple_release(SimpleReleaseRequest)
  → compute_simple_release_plan()         # release/simple.py
      git.ensure_clean_worktree()
      prepare_simple_target()             # auto-detect language if not set
      resolve_current_version()           # from tags or default
      resolve_next_version()              # bump or explicit
      plan_simple_release()               # pure ReleasePlan
  → executor.execute(ReleasePlan)         # release/executor.py
      _apply_manifest_updates()
      _commit_release()
      _create_tags()
      _push_release()                     # branch first, then tags
```

Dry-run skips all Git writes and returns a success result with the planned tag
names.

### Monorepo mode

Same shape but driven by `compute_monorepo_release_plan()` in
`release/monorepo.py`, which:

1. Loads package declarations from `ResolvedConfig.monorepo.packages`.
2. Calls `find_changed_packages()` to detect which packages have commits since
   their last tag.
3. Computes a per-package next version.
4. Produces one `ReleasePlan` with multiple `PackageReleasePlan` entries — one
   commit, multiple tags.

Default monorepo tag template: `v{version}-{package}`.

---

## Error hierarchy

```
DistliftError
  ConfigurationError      invalid or missing config
  GitStateError           dirty worktree, failed git command
  VersionError            malformed version, invalid bump for format
  ManifestUpdateError     failed read or write of manifest file
  ReleasePlanError        cannot build a valid release plan
  UnsupportedLanguageError no plugin registered for the requested language
  PublishError            build or publish of artifacts failed
  PluginError             discovery, loading, or registration failure
```

All are in `src/distlift/errors.py`.

---

## Quality gate

```
ruff check .
ruff format --check .
pytest
```

Run these before committing. `make check` runs all three. `make test` runs
pytest alone. `make install` installs the package in editable mode with dev
dependencies.

---

## Python code style

### Comments on logical blocks

Logical blocks of code must start with a comment describing what that block
does. The comment must be preceded by a blank line.

```python
# Validate the bump kind is compatible with the configured format
validate_bump_allowed(config.version_format, bump)

# Resolve the current version from existing tags or the default
current = resolve_current_version(tags, template, fmt, default_version)
```

### Class docstrings and attribute documentation

All classes must have docstrings. Class docstrings must document every class
attribute, including private ones.

```python
@attrs.define
class ReleasePlan:
    """A fully computed, side-effect-free description of one release run.

    Attributes:
        mode: Whether this is a simple or monorepo release.
        packages: One entry per package being released in this run.
        commit_message: The Git commit message to use.
        tag_names: All tag names to create (one per package).
        remotes: Remote names to push the commit and tags to.
        dry_run: When True the executor logs actions but does not write.
        repo_root: Absolute path to the root of the repository.
    """

    mode: ReleaseMode
    packages: list[PackageReleasePlan]
    commit_message: str
    tag_names: list[str]
    remotes: list[str]
    dry_run: bool
    repo_root: Path
```

### Attribute declaration order

Class attributes must be declared with explicit types directly after the class
docstring, with one blank line separating the docstring from the first
attribute. Public attributes come first, private attributes after, separated
from the public group by a blank line.

```python
@attrs.define
class PluginManager:
    """Coordinates plugin discovery, loading, ordering, and registry creation.

    Attributes:
        registry: The registry built from the last build_registry() call.
        _load_log: Internal record of each plugin load attempt.
    """

    registry: PluginRegistry | None = None

    _load_log: list[str] = attrs.Factory(list)
```

### Function and method docstrings

All functions and methods (public or private) must have docstrings.
Docstrings must document every argument with its type.

```python
def bump_version(parts: VersionParts, bump: BumpKind) -> VersionParts:
    """Return new VersionParts with the given component incremented.

    Args:
        parts: The current version to bump.
        bump: Which component (major, minor, or patch) to increment.
    """
```

This rule applies to functions defined inside other functions too.

### TYPE_CHECKING imports

Imports that are only needed for type annotations must be placed under
`TYPE_CHECKING` and referenced as strings in annotations (because
`from __future__ import annotations` is in effect).

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from distlift.release.models import ReleaseTarget
```

Do not import at module level purely to satisfy a type annotation.

### Avoid `getattr` for known classes

When the class is known and the attribute's existence is certain, access it
directly instead of using `getattr`.

```python
# wrong
name = getattr(plugin, "get_name")()

# right
name = plugin.get_name()
```

---

## Testing conventions

- Tests live under `tests/` in a directory structure that mirrors
  `src/distlift/`.
- Each test file is named `<module>_test.py`.
- Tests that require a real Git repository use the `tmp_git_repo`,
  `tmp_python_project`, or `tmp_js_project` fixtures from `tests/conftest.py`.
- Pure-logic tests (versioning, config, models) need no fixtures and run in
  milliseconds.
- Integration tests that call `git` subprocess commands are slower (~0.5 s per
  subprocess call on Windows) — keep them focused.
- Dry-run paths must be tested; they exercise the planner without side effects.

---

## Adding a new language

1. Create `src/distlift/languages/<name>.py` with a `<Name>ProjectAdapter`
   (subclass `ProjectAdapter`) and a `<Name>ProjectPlugin` (subclass
   `LanguagePlugin`).
2. Add a manifest handler in `src/distlift/manifests/<name>_file.py`.
3. Register the plugin by appending it to `build_builtin_plugins()` in
   `src/distlift/plugins/builtins.py`.
4. Add adapter and manifest tests under `tests/languages/` and (optionally)
   `tests/manifests/`.

## Adding a new config field

1. Add the field to `RawConfig` and `ResolvedConfig` in `config/models.py`.
2. Parse it from TOML in `_parse_raw_config()` in `config/loader.py`.
3. Parse it from the environment in `load_environment_config()`.
4. Merge it in `merge_config_layers()` in `config/merger.py`.
5. Validate it in `config/validators.py` if it has semantic constraints.
6. Expose it in the `config show` command output in `cli.py`.

Changelog settings use a shallow `[changelog]` table merged into
`RawConfig.changelog_overlay`. To add a new changelog key, extend
`_CHANGELOG_ALLOWED_KEYS` and `changelog_from_merged_overlay()` in
`config/loader.py` / `config/merger.py`, validate when needed in
`validate_changelog_config()`, and document any `DISTLIFT_CHANGELOG_*` mapping.
