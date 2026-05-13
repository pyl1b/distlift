from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import attrs

from distlift.constants import (
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
    """

    name: str
    path: str
    language: Language | None = None
    manifest_path: str | None = None
    version_format: VersionFormat = VersionFormat.MAJOR_MINOR_PATCH
    default_version: str = DEFAULT_VERSION
    tag_template: str | None = None
    version_source: VersionSource = VersionSource.MANIFEST


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
        plugins: Plugin-related fields contributed by this layer.
        monorepo: Monorepo section contributed by this layer.
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
    plugins: PluginConfig = attrs.Factory(PluginConfig)
    monorepo: MonorepoConfig = attrs.Factory(MonorepoConfig)
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
        plugins: Effective plugin discovery and override settings.
        monorepo: Effective monorepo enable flag and merged package list.
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
    plugins: PluginConfig = attrs.Factory(PluginConfig)
    monorepo: MonorepoConfig = attrs.Factory(MonorepoConfig)
    field_sources: dict[str, str] = attrs.Factory(dict)
