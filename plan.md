# Distlift Implementation Plan

## Goal

Build `distlift` as both:

- an installable Python library;
- a command line tool;
- a release orchestrator for Python and JavaScript packages;
- a tool that works for single-package repositories and monorepos.

The first implementation should target Python `3.11`, `3.12`, `3.13`, and
newer compatible releases when available.

## Product Scope

The requested behavior splits naturally into two release modes.

### Simple Mode

For a single package or a repository-level release:

1. Resolve configuration from CLI, environment, local config, user config,
   system config, and built-in defaults.
2. Detect the target language, currently `python` or `javascript`.
3. Verify the Git repository is clean.
4. Determine the current version from existing tags, or fall back to a
   configurable default such as `0.1.0`.
5. Apply one of:
   - explicit version via CLI;
   - `--major`;
   - `--minor`;
   - `--patch`.
6. Validate that the requested bump is compatible with the configured version
   format:
   - `major`;
   - `major-minor`;
   - `major-minor-patch`.
7. Update language-specific manifest files when the project stores the version
   in source files.
8. Skip manifest version updates when the project derives version from Git tags
   such as Python `dynamic = ["version"]`.
9. Commit the version update.
10. Create the new tag.
11. Push the commit and tag to one or more configured remotes.

### Monorepo Mode

For repositories with multiple independently versioned packages:

1. Load a root configuration that declares managed packages.
2. Determine the last tag for each managed package.
3. Find packages with changes since their own last tag.
4. Compute the next version only for changed packages.
5. Update only the manifests that belong to changed packages.
6. Create one commit containing all package version changes for the release
   run.
7. Create one tag per changed package, allowing multiple tags on the same
   commit.
8. Push the commit and all created tags to one or more configured remotes.

## Guiding Principles

- Prefer modern Python packaging with `pyproject.toml` and PEP 621 metadata.
- Keep the library API explicit and typed.
- Use `attrs` models instead of built-in dataclasses.
- Keep configuration deterministic and fully traceable.
- Separate pure decision logic from side effects such as Git and file writes.
- Make most functionality plugin-based so users can extend or replace built-in
  behavior.
- Design language support through adapters so more ecosystems can be added
  later.
- Keep release behavior safe by default and fail fast on ambiguous states.

## Recommended Technology Choices

These are the implementation defaults I recommend unless you decide
otherwise:

- Build backend: `hatchling`.
- CLI framework: `typer`.
- Testing framework: `pytest`.
- Linting and formatting: `ruff`.
- Type checking: `mypy` in the dev toolchain.
- Pre-commit automation: `pre-commit`.
- TOML parsing: stdlib `tomllib`.
- JSON parsing: stdlib `json`.
- Structured models: `attrs`.
- Git integration: subprocess wrappers around `git`, not a Git Python binding.
- Plugin discovery: Python entry points plus filesystem-based loading.
- Distribution entry point: `distlift` console script.

`ruff` should be part of the test and validation pipeline, but it should not
replace behavioral tests. The quality gate should be:

```text
ruff check .
ruff format --check .
pytest
```

## Proposed Repository Layout

The project is currently almost empty, so the structure can be designed cleanly
from the start.

```text
distlift/
  README.md
  plan.md
  pyproject.toml
  .pre-commit-config.yaml
  Makefile
  src/
    distlift/
      __init__.py
      __main__.py
      cli.py
      errors.py
      logging_utils.py
      constants.py
      app.py
      plugins/
        __init__.py
        base.py
        discovery.py
        loader.py
        manager.py
        registry.py
        builtins.py
      config/
        __init__.py
        models.py
        loader.py
        merger.py
        discovery.py
        validators.py
      versioning/
        __init__.py
        models.py
        parser.py
        formatter.py
        bump.py
        resolver.py
      vcs/
        __init__.py
        git.py
        tags.py
      languages/
        __init__.py
        base.py
        python.py
        javascript.py
      manifests/
        __init__.py
        pyproject_file.py
        package_json_file.py
      release/
        __init__.py
        models.py
        planner.py
        simple.py
        monorepo.py
        executor.py
      monorepo/
        __init__.py
        discovery.py
        change_detector.py
      publish/
        __init__.py
        models.py
        python.py
        javascript.py
  tests/
    conftest.py
    cli_test.py
    config/
      loader_test.py
      merger_test.py
      validators_test.py
    versioning/
      parser_test.py
      formatter_test.py
      bump_test.py
      resolver_test.py
    vcs/
      git_test.py
      tags_test.py
    languages/
      python_test.py
      javascript_test.py
    release/
      simple_test.py
      monorepo_test.py
      executor_test.py
    monorepo/
      discovery_test.py
      change_detector_test.py
    publish/
      python_test.py
      javascript_test.py
```

## Package-Level Design

### `src/distlift/__init__.py`

Purpose:

- expose package version metadata if desired;
- export a stable public API surface for library consumers.

Planned symbols:

- `__all__`
- `__version__` or a lazy `get_package_version()`

Notes:

- If runtime version derivation becomes inconvenient for the package itself,
  keep the library version static and independent from release target version
  logic.

### `src/distlift/__main__.py`

Purpose:

- support `python -m distlift`.

Planned functions:

- `main() -> None`

Behavior:

- delegate directly to the CLI application.

### `src/distlift/cli.py`

Purpose:

- define the command line interface;
- map CLI options to the internal application service.

Planned functions:

- `build_cli_app() -> typer.Typer`
- `release_simple_command(...) -> None`
- `release_monorepo_command(...) -> None`
- `list_config_command(...) -> None`
- `validate_config_command(...) -> None`
- `list_plugins_command(...) -> None`

Planned option groups:

- shared options:
  - `--language`
  - `--config`
  - `--plugin`
  - `--plugin-dir`
  - `--no-env-plugins`
  - `--remote`
  - `--default-version`
  - `--version-format`
  - `--dry-run`
  - `--verbose`
- simple mode version selectors:
  - `--major`
  - `--minor`
  - `--patch`
  - `--version`
- monorepo selectors:
  - `--package`
  - `--all-changed`
  - `--default-bump`

Important validation rules:

- exactly one version selector must be provided unless configuration supplies
  the default release policy;
- `--patch` must fail for `major` and `major-minor` formats where patch is not
  valid;
- `--minor` must fail for `major` format;
- explicit `--version` must match the configured format.

Plugin-related behavior:

- `--plugin` can be repeated and accepts a plugin file path or a plugin
  package path;
- `--plugin-dir` can be repeated and loads every plugin found in the given
  directory;
- `--no-env-plugins` disables automatic discovery from the active Python
  environment;
- `distlift plugins list` should explain which plugins were discovered,
  loaded, skipped, or overridden.

### `src/distlift/app.py`

Purpose:

- provide a stable orchestration boundary between CLI and core logic.

Planned classes:

- `DistliftApplication`

Planned methods:

- `run_simple_release(self, request: SimpleReleaseRequest) -> ReleaseResult`
- `run_monorepo_release(self, request: MonorepoReleaseRequest) -> ReleaseResult`
- `load_effective_config(self, request: CliConfigRequest) -> ResolvedConfig`
- `load_plugins(self, request: CliPluginRequest) -> PluginRegistry`

Rationale:

- The CLI remains thin, and most behavior becomes directly testable.

### `src/distlift/plugins/base.py`

Purpose:

- define plugin contracts for extensible release capabilities.

Planned classes:

- `DistliftPlugin`
- `LanguagePlugin`
- `ManifestPlugin`
- `VersionSourcePlugin`
- `PublishPlugin`
- `GitBackendPlugin`

Planned methods:

- `get_name(self) -> str`
- `get_version(self) -> str`
- `register(self, registry: PluginRegistry) -> None`

Design goals:

- built-in features should use the same plugin interfaces as external plugins;
- users should be able to replace built-in implementations with their own;
- most subsystem selection should happen through the plugin registry.

### `src/distlift/plugins/registry.py`

Purpose:

- hold the active plugin implementations used by the application.

Planned classes:

- `PluginRegistry`
- `RegisteredPlugin`

Planned methods:

- `register_language_plugin(self, plugin: LanguagePlugin) -> None`
- `register_manifest_plugin(self, plugin: ManifestPlugin) -> None`
- `register_publish_plugin(self, plugin: PublishPlugin) -> None`
- `register_git_backend_plugin(self, plugin: GitBackendPlugin) -> None`
- `get_language_plugin(self, language: str) -> LanguagePlugin`
- `get_manifest_plugin(self, kind: str) -> ManifestPlugin`
- `get_publish_plugin(self, language: str) -> PublishPlugin | None`
- `get_git_backend(self) -> GitBackendPlugin`

Behavior:

- resolve conflicts deterministically;
- allow later-loaded plugins to override earlier ones when enabled;
- retain plugin source metadata for diagnostics.

### `src/distlift/plugins/discovery.py`

Purpose:

- discover plugins from the active environment and filesystem paths.

Planned functions:

- `discover_entry_point_plugins() -> list[DiscoveredPlugin]`
- `discover_plugins_from_paths(paths: Sequence[Path]) -> list[DiscoveredPlugin]`
- `discover_plugins_from_directory(path: Path) -> list[DiscoveredPlugin]`
- `expand_plugin_directories(paths: Sequence[Path]) -> list[Path]`

Supported discovery modes:

- installed environment plugins discovered from Python entry points;
- explicitly listed plugin file paths;
- explicitly listed plugin package directory paths;
- a whole directory of plugins loaded by pointing at that directory.

### `src/distlift/plugins/loader.py`

Purpose:

- import plugin modules and instantiate plugin objects.

Planned functions:

- `load_discovered_plugin(candidate: DiscoveredPlugin) -> DistliftPlugin`
- `load_plugins(candidates: Sequence[DiscoveredPlugin]) -> list[DistliftPlugin]`
- `load_plugin_module_from_path(path: Path) -> ModuleType`

Notes:

- filesystem loading should support both a single file and a package
  directory;
- plugin load failures should produce clear diagnostics.

### `src/distlift/plugins/manager.py`

Purpose:

- coordinate discovery, loading, ordering, and registry creation.

Planned classes:

- `PluginManager`
- `PluginLoadRequest`

Planned methods:

- `build_registry(self, request: PluginLoadRequest) -> PluginRegistry`
- `load_builtin_plugins(self) -> list[DistliftPlugin]`
- `load_environment_plugins(self) -> list[DistliftPlugin]`
- `load_explicit_plugins(self, paths: Sequence[Path]) -> list[DistliftPlugin]`

Planned `PluginLoadRequest` fields:

- `plugin_paths`
- `plugin_directories`
- `disable_environment_plugins`
- `disable_builtin_plugins`
- `allow_plugin_override`

Recommended load order:

1. built-in plugins;
2. environment-discovered plugins;
3. explicit plugin paths;
4. plugins discovered from explicitly provided directories.

### `src/distlift/plugins/builtins.py`

Purpose:

- expose all built-in implementations through the plugin system.

Planned functions:

- `build_builtin_plugins() -> list[DistliftPlugin]`

### `src/distlift/errors.py`

Purpose:

- define typed exceptions with clear user-facing meaning.

Planned classes:

- `DistliftError`
- `ConfigurationError`
- `GitStateError`
- `VersionError`
- `ManifestUpdateError`
- `ReleasePlanError`
- `UnsupportedLanguageError`
- `PublishError`

### `src/distlift/logging_utils.py`

Purpose:

- centralize logging setup and verbose tracing.

Planned functions:

- `configure_logging(verbose: bool) -> None`
- `get_logger(name: str) -> logging.Logger`

Notes:

- follow the repository logging rules;
- use `logger.log(1, ...)` for very verbose traces.

### `src/distlift/constants.py`

Purpose:

- store default paths, default remotes, environment prefixes, and tag templates.

Planned constants:

- `ENV_PREFIX = "DISTLIFT_"`
- `DEFAULT_REMOTE = "origin"`
- `DEFAULT_VERSION = "0.1.0"`
- `DEFAULT_LOCAL_CONFIG_FILENAMES`
- `DEFAULT_USER_CONFIG_PATHS`
- `DEFAULT_SYSTEM_CONFIG_PATHS`

## Configuration System

The configuration stack is a major feature and should be implemented as a
first-class subsystem.

### Configuration Precedence

Highest to lowest precedence:

1. CLI flags
2. environment variables
3. local repository config
4. user config
5. system config
6. built-in defaults

### Proposed Config Locations

Repository-local:

- `distlift.toml`
- `.distlift.toml`
- optionally `[tool.distlift]` inside `pyproject.toml`

User-level:

- Linux/macOS: `~/.config/distlift/config.toml`
- Windows: `%APPDATA%/distlift/config.toml`

System-level:

- Linux/macOS: `/etc/distlift/config.toml`
- Windows: `%ProgramData%/distlift/config.toml`

The exact supported set should be finalized in the decisions section.

### `src/distlift/config/models.py`

Purpose:

- define strongly typed config models.

Planned enums:

- `Language`
- `ReleaseMode`
- `VersionFormat`
- `BumpKind`
- `VersionSource`

Planned classes:

- `RemoteConfig`
- `GitConfig`
- `VersionPolicyConfig`
- `ManifestConfig`
- `PythonProjectConfig`
- `JavaScriptProjectConfig`
- `ManagedPackageConfig`
- `MonorepoConfig`
- `RawConfig`
- `ResolvedConfig`

Important fields:

- `language`
- `mode`
- `plugin_paths`
- `plugin_directories`
- `enable_environment_plugins`
- `enable_builtin_plugins`
- `allow_plugin_override`
- `default_version`
- `version_format`
- `remotes`
- `tag_template`
- `version_source`
- `manifest_path`
- `package_path`
- `package_name`
- `monorepo.packages`

### `src/distlift/config/discovery.py`

Purpose:

- locate candidate config files on disk.

Planned functions:

- `discover_local_config_paths(repo_root: Path) -> list[Path]`
- `discover_user_config_paths() -> list[Path]`
- `discover_system_config_paths() -> list[Path]`
- `discover_embedded_pyproject_config(repo_root: Path) -> Path | None`

### `src/distlift/config/loader.py`

Purpose:

- load TOML and environment data into raw config fragments.

Planned functions:

- `load_toml_config(path: Path) -> dict[str, Any]`
- `load_pyproject_tool_config(path: Path) -> dict[str, Any]`
- `load_environment_config(env: Mapping[str, str]) -> dict[str, Any]`
- `load_config_layers(...) -> list[RawConfig]`

Environment variable examples:

- `DISTLIFT_LANGUAGE=python`
- `DISTLIFT_MODE=simple`
- `DISTLIFT_PLUGIN_PATHS=plugins\\a.py,plugins\\b`
- `DISTLIFT_PLUGIN_DIRS=plugins,third_party_plugins`
- `DISTLIFT_ENABLE_ENVIRONMENT_PLUGINS=true`
- `DISTLIFT_DEFAULT_VERSION=0.1.0`
- `DISTLIFT_REMOTES=origin,upstream`
- `DISTLIFT_VERSION_FORMAT=major-minor-patch`

### `src/distlift/config/merger.py`

Purpose:

- merge configuration layers deterministically.

Planned functions:

- `merge_config_layers(layers: Sequence[RawConfig]) -> ResolvedConfig`
- `merge_optional_scalar[T](...) -> T | None`
- `merge_string_list(...) -> list[str]`
- `merge_package_maps(...) -> dict[str, ManagedPackageConfig]`

Required behavior:

- preserve the source of each resolved field for diagnostics;
- allow `list-config` to explain why a value was chosen.

### `src/distlift/config/validators.py`

Purpose:

- validate semantic constraints after merge.

Planned functions:

- `validate_resolved_config(config: ResolvedConfig) -> None`
- `validate_version_policy(config: ResolvedConfig) -> None`
- `validate_monorepo_config(config: ResolvedConfig) -> None`
- `validate_remote_names(config: ResolvedConfig) -> None`

Validation examples:

- unsupported language;
- unsupported mode;
- missing plugin path;
- invalid plugin directory;
- incompatible plugin override collision;
- invalid version format;
- invalid tag template;
- package path missing in monorepo config;
- explicit manifest path missing;
- duplicate package names;
- incompatible bump kind for version format.

## Versioning System

Versioning should be isolated into pure logic modules so it can be tested
exhaustively.

### `src/distlift/versioning/models.py`

Planned classes:

- `VersionParts`
- `VersionSelection`
- `ResolvedVersion`

Suggested `VersionParts` fields:

- `major`
- `minor`
- `patch`
- `format`

### `src/distlift/versioning/parser.py`

Purpose:

- parse tags and version strings.

Planned functions:

- `parse_version(text: str, fmt: VersionFormat) -> VersionParts`
- `parse_tag_version(
  tag: str,
  template: str,
  fmt: VersionFormat,
  ) -> VersionParts`
- `strip_tag_prefix(tag: str) -> str`

Behavior:

- reject malformed versions early;
- parse only versions compatible with the configured format.

### `src/distlift/versioning/formatter.py`

Purpose:

- format versions and tags consistently.

Planned functions:

- `format_version(parts: VersionParts) -> str`
- `format_tag(version: str, package_name: str | None, template: str) -> str`

Examples:

- `v1`
- `v1.2`
- `v1.2.3`
- `v1.2.3-corelib`

### `src/distlift/versioning/bump.py`

Purpose:

- compute the next version.

Planned functions:

- `bump_version(parts: VersionParts, bump: BumpKind) -> VersionParts`
- `coerce_initial_version(text: str, fmt: VersionFormat) -> VersionParts`
- `validate_bump_allowed(fmt: VersionFormat, bump: BumpKind) -> None`

Rules:

- `major` format allows only major bumps or explicit versions with one part;
- `major-minor` allows major and minor;
- `major-minor-patch` allows major, minor, and patch.

### `src/distlift/versioning/resolver.py`

Purpose:

- determine the effective current and next versions.

Planned functions:

- `resolve_current_version(...) -> VersionParts`
- `resolve_next_version(...) -> ResolvedVersion`
- `find_latest_matching_tag(...) -> str | None`

Inputs:

- existing Git tags;
- default version from config;
- explicit version override;
- bump kind;
- tag template;
- package name for monorepo packages.

## Git and Tagging

Git behavior is safety-critical and should be isolated behind a small API.

### `src/distlift/vcs/git.py`

Purpose:

- wrap Git subprocess calls;
- provide higher-level repository operations.

Planned classes:

- `GitRepository`

Planned methods:

- `ensure_clean_worktree(self) -> None`
- `get_tags(self) -> list[str]`
- `get_tags_matching(self, pattern: str) -> list[str]`
- `get_changed_files(self, revspec: str | None) -> list[Path]`
- `commit_all(self, message: str) -> str`
- `create_tag(self, tag_name: str, message: str | None = None) -> None`
- `push_branch(self, remote: str, branch: str) -> None`
- `push_tag(self, remote: str, tag_name: str) -> None`
- `push_tags(self, remote: str, tag_names: Sequence[str]) -> None`
- `get_current_branch(self) -> str`
- `rev_parse(self, ref: str) -> str`
- `tag_exists(self, tag_name: str) -> bool`

Implementation notes:

- use `subprocess.run(..., check=False, text=True, capture_output=True)`;
- translate command failures into `GitStateError`;
- log executed commands at verbose level.

### `src/distlift/vcs/tags.py`

Purpose:

- centralize tag matching and package-specific tag discovery.

Planned functions:

- `build_tag_pattern(template: str, package_name: str | None) -> str`
- `find_latest_tag_for_package(...) -> str | None`
- `sort_tags_by_version(...) -> list[str]`

## Language Adapters

Language support should use a common interface so new ecosystems can be added
without changing release orchestration. These adapters should be selectable
primarily through the plugin system instead of hard-coded branching.

### `src/distlift/languages/base.py`

Planned classes:

- `ProjectAdapter`

Planned methods:

- `detect_project(self, root: Path) -> bool`
- `load_release_target(
  self,
  root: Path,
  config: ResolvedConfig,
  ) -> ReleaseTarget`
- `is_dynamic_version(self, target: ReleaseTarget) -> bool`
- `read_manifest_version(self, target: ReleaseTarget) -> str | None`
- `update_manifest_version(self, target: ReleaseTarget, version: str) -> None`
- `build_distributions(self, target: ReleaseTarget) -> list[Path]`
- `publish_distributions(self, target: ReleaseTarget) -> None`

### `src/distlift/languages/python.py`

Purpose:

- support Python packages driven by `pyproject.toml`.

Planned classes:

- `PythonProjectAdapter`

Planned methods:

- `detect_project(...)`
- `load_release_target(...)`
- `is_dynamic_version(...)`
- `read_manifest_version(...)`
- `update_manifest_version(...)`
- `build_distributions(...)`
- `publish_distributions(...)`

Detailed Python behavior:

- detect `pyproject.toml`;
- inspect `[project]`;
- if `dynamic = ["version"]`, skip writing the version field;
- otherwise update `project.version`;
- later support tool-specific version locations if needed.

### `src/distlift/languages/javascript.py`

Purpose:

- support JavaScript packages driven by `package.json`.

Planned classes:

- `JavaScriptProjectAdapter`

Planned methods:

- same shape as the Python adapter.

Detailed JavaScript behavior:

- detect `package.json`;
- read and update `"version"` when version is stored in the manifest;
- support future derived-from-tag workflows through config rather than manifest
  introspection.

## Manifest File Updaters

Keeping manifest edits separate from adapters will make file rewrites easier to
test.

### `src/distlift/manifests/pyproject_file.py`

Planned functions:

- `read_pyproject(path: Path) -> dict[str, Any]`
- `project_uses_dynamic_version(data: dict[str, Any]) -> bool`
- `get_project_version(data: dict[str, Any]) -> str | None`
- `set_project_version(path: Path, version: str) -> None`

Important note:

- Python stdlib can read TOML, but not preserve formatting on write.
- A decision is needed on whether to use a TOML writer library or implement a
  minimal controlled rewrite strategy.

### `src/distlift/manifests/package_json_file.py`

Planned functions:

- `read_package_json(path: Path) -> dict[str, Any]`
- `get_package_version(data: dict[str, Any]) -> str | None`
- `set_package_version(path: Path, version: str) -> None`

## Release Models and Orchestration

### `src/distlift/release/models.py`

Planned classes:

- `ReleaseTarget`
- `SimpleReleaseRequest`
- `MonorepoReleaseRequest`
- `PackageReleasePlan`
- `ReleasePlan`
- `ReleaseResult`

Suggested `ReleasePlan` fields:

- `mode`
- `targets`
- `next_versions`
- `manifest_updates`
- `commit_message`
- `tag_names`
- `remotes`
- `dry_run`

### `src/distlift/release/planner.py`

Purpose:

- build pure release plans before any side effects happen.

Planned functions:

- `plan_simple_release(...) -> ReleasePlan`
- `plan_monorepo_release(...) -> ReleasePlan`
- `build_commit_message(...) -> str`
- `build_tag_messages(...) -> dict[str, str]`

### `src/distlift/release/simple.py`

Purpose:

- implement simple mode planning details.

Planned functions:

- `prepare_simple_target(...) -> ReleaseTarget`
- `compute_simple_release_plan(...) -> ReleasePlan`

Flow:

1. resolve config;
2. detect project;
3. ensure clean Git state;
4. resolve current version;
5. compute next version;
6. update manifest if needed;
7. plan commit;
8. plan tag creation;
9. plan pushes.

### `src/distlift/release/monorepo.py`

Purpose:

- implement monorepo-specific planning.

Planned functions:

- `discover_managed_targets(...) -> list[ReleaseTarget]`
- `select_changed_targets(...) -> list[ReleaseTarget]`
- `compute_monorepo_release_plan(...) -> ReleasePlan`

Flow:

1. read root monorepo package declarations;
2. resolve each package's last tag;
3. diff changed files per package;
4. keep only changed packages;
5. compute next version per package;
6. update manifests for changed packages only;
7. build one commit and many tags.

### `src/distlift/release/executor.py`

Purpose:

- execute a precomputed release plan.

Planned classes:

- `ReleaseExecutor`

Planned methods:

- `execute(self, plan: ReleasePlan) -> ReleaseResult`
- `_apply_manifest_updates(self, plan: ReleasePlan) -> None`
- `_commit_release(self, plan: ReleasePlan) -> str`
- `_create_tags(self, plan: ReleasePlan) -> None`
- `_push_release(self, plan: ReleasePlan) -> None`

Execution order:

1. apply manifest updates;
2. create commit;
3. create tags;
4. push branch;
5. push tags.

The branch push should likely be mandatory if a new commit was created, because
remote tags must not point to an unpublished commit.

## Monorepo Support

### `src/distlift/monorepo/discovery.py`

Purpose:

- load and normalize monorepo package declarations.

Planned functions:

- `load_managed_packages(config: ResolvedConfig) -> list[ManagedPackageConfig]`
- `resolve_package_manifest_path(package: ManagedPackageConfig) -> Path`

Suggested package declaration fields:

- `name`
- `path`
- `language`
- `manifest_path`
- `version_format`
- `default_version`
- `tag_template`
- `version_source`

### `src/distlift/monorepo/change_detector.py`

Purpose:

- determine which managed packages changed since their last release tag.

Planned functions:

- `find_changed_packages(...) -> list[ManagedPackageConfig]`
- `find_package_last_tag(...) -> str | None`
- `package_has_changes_since_tag(...) -> bool`

Change detection algorithm:

1. locate the last tag for a package using its tag template;
2. if no tag exists, compare from repository start or treat as changed;
3. obtain changed files with `git diff --name-only`;
4. mark a package as changed when at least one changed file is under its path.

Future extension:

- dependency-aware cascading version bumps between packages.

## Publish Support

The described workflow is release-centric today, but the tool's stated purpose
includes creating and pushing distributions. The design should reserve explicit
space for that.

### `src/distlift/publish/models.py`

Planned classes:

- `BuildArtifact`
- `PublishRequest`
- `PublishResult`

### `src/distlift/publish/python.py`

Planned functions:

- `build_python_distributions(...) -> list[BuildArtifact]`
- `publish_python_distributions(...) -> PublishResult`

Recommended future tools:

- `python -m build`
- `uv publish` or `twine upload`

### `src/distlift/publish/javascript.py`

Planned functions:

- `build_javascript_distributions(...) -> list[BuildArtifact]`
- `publish_javascript_distributions(...) -> PublishResult`

Recommended future tools:

- `npm pack`
- `npm publish`

The first implementation can stop at tag-and-push release automation if you
want to ship a smaller MVP, but the internal design should not block later
build and publish subcommands.

## Plugin Architecture

Plugin support should be a first-class design goal.

### Extensibility Goals

- allow built-in behavior to be implemented through the same interfaces as
  external plugins;
- allow users to replace built-in tools with user-provided alternatives;
- allow users to add support for new languages, manifest formats, and publish
  providers without modifying core code;
- keep plugin loading explicit and diagnosable.

### Plugin Capability Areas

Most major capabilities should be plugin-based:

- language detection and project adaptation;
- manifest reading and version writing;
- version-source resolution for tag-derived or externally-derived versions;
- Git backend operations;
- distribution build and publish providers.

### Plugin Discovery Sources

The tool should support three discovery mechanisms.

1. Environment plugins

- discover installed plugins from Python entry points in the active
  environment;
- load them automatically by default unless disabled.

2. Explicit plugin paths

- accept a list of plugin file paths or package directory paths from CLI or
  config;
- load only those user-selected plugins.

3. Plugin directories

- accept a directory path;
- scan that directory for plugin modules or plugin packages;
- load every valid plugin found inside it.

### Plugin Configuration Shape

The resolved configuration should support plugin controls such as:

```toml
[plugins]
enable_environment = true
enable_builtin = true
allow_override = true
paths = ["./plugins/custom_git.py", "./plugins/company_release"]
directories = ["./plugins", "./vendor/distlift_plugins"]
```

### Plugin Resolution Rules

- built-ins are loaded first;
- environment-discovered plugins are loaded after built-ins;
- explicitly listed plugin paths are loaded after environment plugins;
- explicitly listed plugin directories are loaded last;
- later-loaded plugins may override earlier ones when overrides are enabled;
- diagnostics should show plugin name, source, and overridden capability.

### Plugin Example Use Cases

- replace the built-in Git backend with a company-specific wrapper;
- load a custom JavaScript publisher;
- add support for a new language ecosystem;
- replace the built-in manifest updater with one that enforces local rules.

## CLI Shape

Recommended initial CLI:

```text
distlift release simple --language python --patch
distlift release simple --language javascript --minor
distlift release simple --plugin .\plugins\custom_git.py --patch
distlift release simple --plugin-dir .\plugins --patch
distlift release simple --language python --version 2.4.0
distlift release monorepo --all-changed --default-bump patch
distlift config show
distlift config validate
distlift plugins list
```

Potential future CLI:

```text
distlift build --language python
distlift publish --language javascript
distlift release simple --publish
```

## Example Configuration Shape

Repository-local config can be centered on a dedicated TOML file.

```toml
[release]
mode = "simple"
language = "python"
default_version = "0.1.0"
version_format = "major-minor-patch"
remotes = ["origin"]
tag_template = "v{version}"
version_source = "manifest"

[plugins]
enable_environment = true
enable_builtin = true
allow_override = true
paths = ["./plugins/custom_git.py"]
directories = ["./plugins"]

[monorepo]
enabled = false

[[monorepo.packages]]
name = "corelib"
path = "packages/corelib"
language = "python"
manifest_path = "packages/corelib/pyproject.toml"
tag_template = "v{version}-corelib"
version_format = "major-minor-patch"
default_version = "0.1.0"
version_source = "manifest"
```

Environment variables should map cleanly to this model for top-level values.
For nested monorepo package declarations, file-based config is the better
primary mechanism.

## File-by-File Implementation Plan

### Phase 1: Project Bootstrap

Files to create later:

- `pyproject.toml`
- `.pre-commit-config.yaml`
- `Makefile`
- `src/distlift/...`
- `tests/...`

Concrete tasks:

- configure package metadata and console entry point;
- define a plugin entry-point group such as `distlift.plugins`;
- add Python `>=3.11`;
- add dev dependencies for `pytest`, `ruff`, `mypy`, and `pre-commit`;
- configure `ruff check` and `ruff format`;
- add `pytest` settings and coverage defaults;
- wire pre-commit hooks for formatting, linting, and basic repo hygiene.

### Phase 2: Core Models and Pure Logic

Files:

- `plugins/base.py`
- `plugins/registry.py`
- `config/models.py`
- `versioning/models.py`
- `versioning/parser.py`
- `versioning/formatter.py`
- `versioning/bump.py`

Concrete tasks:

- implement plugin capability interfaces;
- implement the plugin registry;
- implement enums and attrs models;
- implement version parsing and formatting;
- implement bump validation rules;
- add exhaustive tests for allowed and rejected versions.

### Phase 3: Config Resolution

Files:

- `plugins/discovery.py`
- `plugins/loader.py`
- `plugins/manager.py`
- `config/discovery.py`
- `config/loader.py`
- `config/merger.py`
- `config/validators.py`

Concrete tasks:

- discover environment plugins through entry points;
- load plugins from explicit file and package paths;
- load all plugins from user-provided plugin directories;
- discover config files;
- load TOML and environment sources;
- merge layers with precedence tracking;
- validate effective configuration;
- expose `distlift config show` and `distlift config validate`.

### Phase 4: Git Integration

Files:

- `vcs/git.py`
- `vcs/tags.py`
- `plugins/builtins.py`

Concrete tasks:

- wrap `git status`, `git tag`, `git diff`, `git commit`, and `git push`;
- expose the Git CLI backend through the plugin registry;
- implement package-specific tag lookup;
- add tests with temporary repositories.

### Phase 5: Language Adapters and Manifest Writers

Files:

- `languages/base.py`
- `languages/python.py`
- `languages/javascript.py`
- `manifests/pyproject_file.py`
- `manifests/package_json_file.py`

Concrete tasks:

- detect project language;
- read and update current manifest version;
- implement dynamic-version skip for Python;
- decide how TOML writes preserve formatting;
- expose built-in language and manifest support as plugins;
- add adapter tests with fixture projects.

### Phase 6: Simple Release Mode

Files:

- `release/models.py`
- `release/planner.py`
- `release/simple.py`
- `release/executor.py`
- `app.py`
- `cli.py`

Concrete tasks:

- build the simple release plan;
- resolve active implementations through the plugin registry;
- support explicit version and bump flags;
- create commit and tag;
- push commit and tags to one or more remotes;
- add dry-run support;
- add end-to-end tests with temporary Git repositories.

### Phase 7: Monorepo Release Mode

Files:

- `monorepo/discovery.py`
- `monorepo/change_detector.py`
- `release/monorepo.py`

Concrete tasks:

- load managed package declarations;
- resolve per-package language support through plugins;
- discover changed packages since their last tags;
- compute per-package versions;
- update only changed manifests;
- create multiple tags for one commit;
- add monorepo integration tests.

### Phase 8: Distribution Build and Publish

Files:

- `publish/models.py`
- `publish/python.py`
- `publish/javascript.py`

Concrete tasks:

- define artifact build and publish contracts;
- support Python build and upload tooling;
- support JavaScript pack and publish tooling;
- integrate publish as an optional release step.

## Testing Strategy

The tests should mirror the package structure and use temporary directories and
temporary Git repositories heavily.

### Unit Test Focus

- plugin discovery and conflict resolution;
- plugin path and directory loading;
- config precedence;
- config validation;
- version parsing;
- version bump rules;
- tag formatting;
- manifest version detection;
- package change detection.

### Integration Test Focus

- environment plugin auto-discovery;
- explicit plugin path loading;
- plugin directory scanning and bulk loading;
- replacement of a built-in implementation by a user plugin;
- simple mode release in a Python repository;
- simple mode release in a JavaScript repository;
- monorepo release with one changed package;
- monorepo release with multiple changed packages;
- dynamic Python version mode with no manifest rewrite;
- multi-remote push planning;
- rejected dirty worktree scenarios.

### Suggested Test Classes

- `TestPluginDiscovery`
- `TestPluginLoader`
- `TestPluginRegistry`
- `TestPluginOverrides`
- `TestParseVersion`
- `TestFormatVersion`
- `TestBumpVersion`
- `TestMergeConfigLayers`
- `TestValidateResolvedConfig`
- `TestGitRepository`
- `TestPythonProjectAdapter`
- `TestJavaScriptProjectAdapter`
- `TestSimpleReleasePlan`
- `TestSimpleReleaseExecution`
- `TestMonorepoChangeDetection`
- `TestMonorepoReleasePlan`

## Pre-Commit Plan

Recommended hooks:

- `ruff-check`
- `ruff-format`
- `end-of-file-fixer`
- `trailing-whitespace`
- `check-merge-conflict`
- `check-toml`
- `check-yaml`

Optional hooks:

- `mypy`
- `pytest` for smaller test subsets

I recommend keeping `pytest` out of the default pre-commit run if execution
time becomes annoying, and instead enforcing it in CI and local `make test`.

## Detailed TODO List

### Bootstrap TODOs

- create `pyproject.toml` with PEP 621 metadata;
- add a console script entry point named `distlift`;
- define a plugin entry-point group such as `distlift.plugins`;
- select the build backend;
- define dev dependencies;
- configure `ruff`, `pytest`, and `mypy`;
- add `.pre-commit-config.yaml`;
- add `Makefile` targets matching repository conventions.

### Core Model TODOs

- implement `DistliftPlugin` and capability-specific plugin interfaces;
- implement `PluginRegistry`;
- implement `Language`, `ReleaseMode`, `VersionFormat`, `BumpKind`, and
  `VersionSource`;
- implement `ResolvedConfig`;
- implement `ReleasePlan` and `ReleaseResult`;
- implement `VersionParts`.

### Config TODOs

- implement plugin config schema;
- implement local, user, and system config discovery;
- implement env var parsing with the `DISTLIFT_` prefix;
- implement config merge precedence;
- implement config source tracing for diagnostics;
- implement semantic config validation;
- implement `distlift config show`;
- implement `distlift config validate`.

### Versioning TODOs

- implement version parsing for `major`, `major-minor`, and
  `major-minor-patch`;
- implement version bumping rules;
- implement explicit version validation;
- implement tag parsing from configurable templates;
- implement latest matching tag resolution.

### Git TODOs

- implement clean worktree detection;
- implement tag listing and filtering;
- implement changed file detection;
- implement commit creation;
- implement tag creation;
- implement branch push;
- implement tag push to multiple remotes;
- implement friendly Git error translation.

### Plugin TODOs

- implement environment discovery through Python entry points;
- implement explicit plugin file loading;
- implement explicit plugin package loading;
- implement whole-directory plugin scanning;
- implement deterministic plugin override rules;
- implement plugin source diagnostics;
- implement built-in plugins through the same registry as external plugins;
- implement `distlift plugins list` diagnostics.

### Python Adapter TODOs

- detect `pyproject.toml`;
- read `[project]` metadata;
- detect `dynamic = ["version"]`;
- update `project.version` when appropriate;
- skip manifest updates for dynamic version projects.

### JavaScript Adapter TODOs

- detect `package.json`;
- read current `"version"`;
- update `"version"` safely;
- define config-driven support for tag-derived versioning.

### Simple Mode TODOs

- validate version selector arguments;
- resolve current version from tags;
- compute next version;
- update manifests when needed;
- generate commit message;
- create tag name;
- push to configured remotes;
- support dry-run output.

### Monorepo TODOs

- define monorepo package config schema;
- load managed package declarations;
- locate last tag per package;
- find changed packages since last tag;
- compute next version per package;
- update only changed package manifests;
- build one commit and many tags;
- support package filtering via CLI.

### Publish TODOs

- decide if publish ships in MVP or later;
- define artifact model;
- add Python build support;
- add Python publish support;
- add JavaScript pack support;
- add JavaScript publish support.

### QA TODOs

- add unit tests for all pure logic;
- add integration tests for Git workflows;
- add integration tests for manifest updates;
- add integration tests for monorepo releases;
- add CI workflow later for Python version matrix.

## Decisions Needed

These are the places where I recommend pausing for your choice before
implementation starts.

### 1. CLI Framework

Decision:

- use `typer`.

Why this matters:

- `typer` gives a cleaner modern CLI experience and better typing support;
- `argparse` keeps the dependency set smaller.

### 2. Build Backend

Decision:

- use `hatchling`.

Alternatives:

- `setuptools`
- `pdm-backend`

Why this matters:

- this affects packaging metadata, build flow, and long-term ergonomics.

### 3. Local Config Shape

Decision:

- `distlift.toml` plus optional `[tool.distlift]` in `pyproject.toml`;

Recommendation:

- support `distlift.toml` plus optional `[tool.distlift]` in `pyproject.toml`.

Why this matters:

- it affects portability across languages and how easy cross-language monorepos
  are to manage.

### 4. Plugin Packaging Contract

Question:

- should filesystem plugins be a single Python file, a Python package
  directory, or both?

Decision:

- both single-file plugins and package-directory plugins should be supported.

Recommendation:

- support both from the start.

Why this matters:

- single files are convenient for small customizations, while package
  directories scale better for richer extensions.

### 5. Plugin Discovery Defaults

Question:

- should environment-discovered plugins load automatically, or only when
  explicitly enabled?

Decision:

- environment plugins should load automatically by default.

Recommendation:

- keep `--no-env-plugins` and config support so users can disable automatic
  discovery when they want tighter control.

Why this matters:

- automatic loading is convenient, but some environments need strict
  predictability.

### 6. Exact Tag Format for Monorepo Packages

You described tags like `vM.m.p-xxx`. The exact template should be chosen.

Decision:

- `v{version}-{package}`

Recommendation:

- default to `v{version}-{package}` because it matches your example most
  closely.

### 7. Commit Push Behavior

Question:

- should the tool push only tags, or always push the commit too?

Decision:

- always push the commit first, then push tags.

Why this matters:

- a remote tag pointing at a commit that only exists locally is dangerous and
  confusing.

### 8. TOML Rewrite Strategy

Question:

- should we preserve formatting and comments in `pyproject.toml`, or is a
  normalized rewrite acceptable?

Decision:

- use a formatting-preserving TOML library;

Recommendation:

- use a TOML library that can preserve structure well enough for reliable
  version updates.

### 9. JavaScript Tooling Scope

Question:

- should initial JavaScript support assume `npm`, or support `pnpm` and `yarn`
  from day one?

Decision:

- `npm`, `pnpm` and `yarn`

### 10. Publish in MVP or Release-Only MVP

Question:

- should the first release of `distlift` stop at version bump plus Git tagging,
  or also build and publish package artifacts?

Decision:

- the default mode should be that the CI/CD will build and publish, so
  we do nothing on that front
- the user can provide arguments or configuration to indicate that it wants
  build and that it wants publish. The user can indicate a script to use
  for those steps or a command in the configuration files.

### 11. Test Tooling Interpretation

Question:

- when you said "testing using ruff", do you want Ruff only for lint and format,
  or do you want to avoid `pytest` entirely?

Decision:

- use `ruff` for lint and format, and `pytest` for behavior tests.

Why this matters:

- Ruff is excellent for static quality checks, but it is not a replacement for
  release workflow tests.

### 12. First Configured Default Version

Question:

- should the built-in default stay `0.1.0`, or should it be configurable with a
  repo default such as `0.0.1`?

Decision:

- keep built-in `0.1.0`, allow overrides in config and CLI.

## Suggested Delivery Order

If we implement this next, I recommend the following order:

1. Bootstrap the project and quality tooling.
2. Implement config models and version logic.
3. Implement Git wrappers.
4. Implement Python simple mode end to end.
5. Implement JavaScript simple mode end to end.
6. Implement monorepo package discovery and change detection. Use a plugin
   system that either autodetects or lets the user specify which
   plugin should handle the task.
7. Implement monorepo release execution.
8. Implement artifact build and publish support.

This order gets a working Python MVP quickly while keeping the architecture
ready for JavaScript and monorepos.
