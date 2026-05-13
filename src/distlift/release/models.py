from __future__ import annotations

from pathlib import Path

import attrs

from distlift.config.models import (
    BumpKind,
    Language,
    ReleaseMode,
    ResolvedConfig,
    VersionSource,
)
from distlift.versioning.models import ResolvedVersion


@attrs.define
class ReleaseTarget:
    language: Language
    root: Path
    manifest_path: Path
    version_source: VersionSource = VersionSource.MANIFEST
    package_name: str | None = None


@attrs.define
class SimpleReleaseRequest:
    repo_root: Path
    config: ResolvedConfig
    bump: BumpKind | None = None
    explicit_version: str | None = None
    dry_run: bool = False


@attrs.define
class MonorepoReleaseRequest:
    repo_root: Path
    config: ResolvedConfig
    default_bump: BumpKind = BumpKind.PATCH
    selected_packages: list[str] = attrs.Factory(list)
    all_changed: bool = True
    dry_run: bool = False


@attrs.define
class PackageReleasePlan:
    target: ReleaseTarget
    resolved_version: ResolvedVersion
    update_manifest: bool


@attrs.define
class ReleasePlan:
    mode: ReleaseMode
    packages: list[PackageReleasePlan]
    commit_message: str
    tag_names: list[str]
    remotes: list[str]
    dry_run: bool
    repo_root: Path

    @property
    def has_manifest_updates(self) -> bool:
        return any(p.update_manifest for p in self.packages)


@attrs.define
class ReleaseResult:
    success: bool
    dry_run: bool
    tag_names: list[str] = attrs.Factory(list)
    commit_sha: str | None = None
    pushed_remotes: list[str] = attrs.Factory(list)
    error: str | None = None
