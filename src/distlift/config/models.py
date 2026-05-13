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
    PYTHON = "python"
    JAVASCRIPT = "javascript"


class ReleaseMode(StrEnum):
    SIMPLE = "simple"
    MONOREPO = "monorepo"


class VersionFormat(StrEnum):
    MAJOR = "major"
    MAJOR_MINOR = "major-minor"
    MAJOR_MINOR_PATCH = "major-minor-patch"


class BumpKind(StrEnum):
    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"


class VersionSource(StrEnum):
    MANIFEST = "manifest"
    TAG = "tag"


@attrs.define
class ManagedPackageConfig:
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
    enabled: bool = False
    packages: list[ManagedPackageConfig] = attrs.Factory(list)


@attrs.define
class PluginConfig:
    enable_environment: bool = True
    enable_builtin: bool = True
    allow_override: bool = True
    paths: list[str] = attrs.Factory(list)
    directories: list[str] = attrs.Factory(list)


@attrs.define
class RawConfig:
    """A single configuration layer loaded from one source."""

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
    """Fully resolved effective configuration after merging all layers."""

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
