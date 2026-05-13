from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

import attrs

from distlift.constants import (
    DEFAULT_DEPLOY_TAG_PREFIX,
    DEFAULT_REMOTE,
    DEFAULT_TAG_TEMPLATE,
    DEFAULT_VERSION,
)


class Language(StrEnum):
    """Project language selector for adapters and manifest handling.

    Attributes:
        PYTHON: Python packages using pyproject-style metadata.
        JAVASCRIPT: JavaScript or Node packages using package.json.
    """

    PYTHON = "python"
    JAVASCRIPT = "javascript"


class ReleaseMode(StrEnum):
    """Whether distlift treats the repository as one package or many.

    Attributes:
        SIMPLE: Single-package repository with one version line.
        MONOREPO: Multiple independently versioned packages under one root.
    """

    SIMPLE = "simple"
    MONOREPO = "monorepo"


class VersionFormat(StrEnum):
    """How many numeric components participate in versions and bumps.

    Attributes:
        MAJOR: Single-component major-only versions.
        MAJOR_MINOR: Major and minor components without patch.
        MAJOR_MINOR_PATCH: Semantic-style major, minor, and patch.
    """

    MAJOR = "major"
    MAJOR_MINOR = "major-minor"
    MAJOR_MINOR_PATCH = "major-minor-patch"


class BumpKind(StrEnum):
    """Which version component to increment for the next release.

    Attributes:
        MAJOR: Increment the major component and reset lower parts.
        MINOR: Increment the minor component when present.
        PATCH: Increment the patch component when present.
    """

    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"


def _default_changelog_skip_types() -> list[str]:
    """Return default conventional-commit types skipped from CHANGELOG."""
    return ["chore", "docs", "style", "test", "ci", "build"]


def _default_changelog_commit_mapping() -> dict[str, str]:
    """Return default mapping from conventional type to Keep a Changelog
    section.
    """
    return {
        "feat": "Added",
        "fix": "Fixed",
        "perf": "Changed",
        "refactor": "Changed",
        "deprecate": "Deprecated",
        "remove": "Removed",
        "security": "Security",
    }


@attrs.define
class ChangelogConfig:
    """Keep a Changelog generation settings merged from configuration layers.

    Attributes:
        enabled: When True, release runs update CHANGELOG.md where configured.
        path: Repository-relative path to CHANGELOG.md for simple mode or
            default.
        title: Top-level document title for scaffolded changelogs.
        header_text: Intro paragraphs inserted when initializing a new file.
        date_format: strftime format for release dates under version headings.
        include_unreleased_section: When True, maintain an ``[Unreleased]``
            section between releases.
        compare_url_template: Compare URL with ``{prev}`` and ``{next}``
            placeholders; empty triggers detection from ``origin``.
        skip_commit_types: Conventional commit types omitted from generated
            lists.
        commit_mapping: Maps conventional type strings to section titles.
        default_section: Section title for non-conventional or unknown types.
        prompt_editor: When True (default), open an editor on the generated
            release entry fragment before writing during interactive releases.
    """

    enabled: bool = True
    path: str = "CHANGELOG.md"
    title: str = "Changelog"
    header_text: str = ""
    date_format: str = "%Y-%m-%d"
    include_unreleased_section: bool = True
    compare_url_template: str = ""
    prompt_editor: bool = True
    skip_commit_types: list[str] = attrs.Factory(_default_changelog_skip_types)
    commit_mapping: dict[str, str] = attrs.Factory(
        _default_changelog_commit_mapping
    )
    default_section: str = "Changed"


@attrs.define
class DeployConfig:
    """Settings for ``distlift deploy`` CI marker tags.

    Attributes:
        tag_prefix: Prefix for numbered tags ``{prefix}_{N}``.
        verify_indexes: When True, require manifest versions to exist on
            PyPI / npm (per language) before creating the tag.
    """

    tag_prefix: str = DEFAULT_DEPLOY_TAG_PREFIX
    verify_indexes: bool = False


class VersionSource(StrEnum):
    """Where the current package version is read from before a bump.

    Attributes:
        MANIFEST: Read the declared version from the project manifest file.
        TAG: Infer the current version from the latest matching Git tag.
    """

    MANIFEST = "manifest"
    TAG = "tag"


@attrs.define
class ManagedPackageConfig:
    """One monorepo package entry loaded from configuration.

    Attributes:
        name: Unique logical name for this package within the monorepo.
        path: Repository-relative directory containing the package root.
        language: Optional override of the global language for this package.
        manifest_path: Optional explicit path to the version manifest file.
        version_format: How many numeric components this package uses.
        default_version: Fallback version when none can be resolved.
        tag_template: Optional per-package tag naming template override.
        version_source: Whether to read the version from manifest or tags.
        changelog_path: Optional override path for this package's CHANGELOG.md.
    """

    name: str
    path: str
    language: Language | None = None
    manifest_path: str | None = None
    version_format: VersionFormat = VersionFormat.MAJOR_MINOR_PATCH
    default_version: str = DEFAULT_VERSION
    tag_template: str | None = None
    version_source: VersionSource = VersionSource.MANIFEST
    changelog_path: str | None = None


@attrs.define
class MonorepoConfig:
    """Monorepo-specific settings merged from all configuration layers.

    Attributes:
        enabled: When True, distlift runs in monorepo release mode.
        packages: Declared packages and their per-package overrides.
    """

    enabled: bool = False
    packages: list[ManagedPackageConfig] = attrs.Factory(list)


@attrs.define
class HookSpec:
    """One command to run as a lifecycle hook.

    Exactly one of ``shell`` or ``argv`` must be set.

    Attributes:
        shell: Full string passed to the shell when ``shell=True``.
        argv: Program name and arguments when ``shell=False``.
    """

    shell: str | None = None
    argv: list[str] | None = None


@attrs.define
class HooksConfig:
    """Lifecycle hook commands merged from configuration layers.

    Each field is a list of :class:`HookSpec` entries for that event
    (TOML and env-append merged by the config merger).

    Attributes:
        tag_pushed: After all tag pushes succeed for a release.
        tag_push_failed: After a Git push step raises (partial remotes may
            be recorded in hook environment).
        release_failed: Planning failure or executor failure except push-only.
        build_succeeded: After a successful local build for one package.
        build_failed: After a failed local build for one package.
        publish_succeeded: After a successful registry upload for one package.
        publish_failed: After a failed registry upload for one package.
    """

    tag_pushed: list[HookSpec] = attrs.Factory(list)
    tag_push_failed: list[HookSpec] = attrs.Factory(list)
    release_failed: list[HookSpec] = attrs.Factory(list)
    build_succeeded: list[HookSpec] = attrs.Factory(list)
    build_failed: list[HookSpec] = attrs.Factory(list)
    publish_succeeded: list[HookSpec] = attrs.Factory(list)
    publish_failed: list[HookSpec] = attrs.Factory(list)


def _empty_hooks_config() -> HooksConfig:
    """Return a ``HooksConfig`` with no hooks registered.

    Args:
        None
    """
    return HooksConfig()


@attrs.define
class PluginConfig:
    """Plugin discovery and override behavior for this configuration.

    Attributes:
        enable_environment: Whether to load plugins from entry points.
        enable_builtin: Whether built-in plugins are registered first.
        allow_override: Whether later plugins may replace earlier ones.
        paths: Explicit filesystem paths to plugin modules or packages.
        directories: Directories scanned for plugin modules.
    """

    enable_environment: bool = True
    enable_builtin: bool = True
    allow_override: bool = True
    paths: list[str] = attrs.Factory(list)
    directories: list[str] = attrs.Factory(list)


@attrs.define
class RawConfig:
    """A single configuration layer loaded from one source.

    Attributes:
        language: Declared primary language, if this layer sets it.
        mode: Simple or monorepo mode, if this layer sets it.
        default_version: Default version string, if this layer sets it.
        version_format: Declared version format, if this layer sets it.
        remotes: Git remote names for pushes from this layer.
        tag_template: Tag naming template including a version placeholder.
        version_source: Whether versions come from manifest or tags.
        manifest_path: Optional explicit manifest path as a string path.
        editor: Optional external editor command used as a fallback when no
            ``GIT_EDITOR`` / ``VISUAL`` / ``EDITOR`` env var is set.
        plugins: Plugin-related fields contributed by this layer.
        monorepo: Monorepo section contributed by this layer.
        changelog_overlay: Optional shallow overlay dict for ``changelog`` keys
            from this layer; merged field-by-field across layers.
        deploy_overlay: Shallow overlay dict for ``[deploy]`` keys from this
            layer; merged field-by-field across layers.
        hooks: Hook commands from this layer's ``[hooks]`` table.
        hooks_append: Extra hook specs parsed from ``DISTLIFT_HOOKS_*``; only
            the environment layer supplies these; appended after TOML merge.
        source: Human-readable label for the origin of this fragment.
    """

    language: Language | None = None
    mode: ReleaseMode | None = None
    default_version: str | None = None
    version_format: VersionFormat | None = None
    remotes: list[str] = attrs.Factory(list)
    tag_template: str | None = None
    version_source: VersionSource | None = None
    manifest_path: str | None = None
    editor: str | None = None
    plugins: PluginConfig = attrs.Factory(PluginConfig)
    monorepo: MonorepoConfig = attrs.Factory(MonorepoConfig)
    changelog_overlay: dict[str, Any] = attrs.Factory(dict)
    deploy_overlay: dict[str, Any] = attrs.Factory(dict)
    hooks: HooksConfig = attrs.Factory(_empty_hooks_config)
    hooks_append: HooksConfig = attrs.Factory(_empty_hooks_config)
    source: str = "<unknown>"


@attrs.define
class ResolvedConfig:
    """Fully merged effective configuration after applying all layers.

    Attributes:
        language: Effective language, if any layer specified one.
        mode: Effective release mode with a non-optional default.
        default_version: Effective default semantic version string.
        version_format: Effective version component layout.
        remotes: Git remotes to push commits and tags to.
        tag_template: Effective tag naming template for this repository.
        version_source: Whether the current version is read from manifest
            or from existing tags.
        manifest_path: Optional absolute manifest path when configured.
        editor: Optional external editor command (e.g. ``"code --wait"``)
            used when the standard editor env vars are unset; ``None`` means
            no config-level fallback was provided.
        plugins: Effective plugin discovery and override settings.
        monorepo: Effective monorepo enable flag and merged package list.
        changelog: Effective Keep a Changelog generation settings.
        deploy: Effective ``distlift deploy`` settings.
        hooks: Effective lifecycle hook command lists.
        field_sources: Map of top-level scalar field names to the source
            label of the layer that last set each field.
    """

    language: Language | None = None
    mode: ReleaseMode = ReleaseMode.SIMPLE
    default_version: str = DEFAULT_VERSION
    version_format: VersionFormat = VersionFormat.MAJOR_MINOR_PATCH
    remotes: list[str] = attrs.Factory(lambda: [DEFAULT_REMOTE])
    tag_template: str = DEFAULT_TAG_TEMPLATE
    version_source: VersionSource = VersionSource.MANIFEST
    manifest_path: Path | None = None
    editor: str | None = None
    plugins: PluginConfig = attrs.Factory(PluginConfig)
    monorepo: MonorepoConfig = attrs.Factory(MonorepoConfig)
    changelog: ChangelogConfig = attrs.Factory(ChangelogConfig)
    deploy: DeployConfig = attrs.Factory(DeployConfig)
    hooks: HooksConfig = attrs.Factory(_empty_hooks_config)
    field_sources: dict[str, str] = attrs.Factory(dict)
