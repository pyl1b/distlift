"""Models for interactive third-party dependency upgrades."""

from __future__ import annotations

from pathlib import Path

import attrs

from distlift.dependencies.models import (
    DependencyProject,
    DependencyUpdateChange,
)


@attrs.define(frozen=True)
class PackageSource:
    """One upgradeable project and its package manager context.

    Attributes:
        project: Distlift dependency project descriptor.
        manager_name: Selected package manager plugin id.
        lock_files: Lock file paths the manager may refresh.
    """

    project: DependencyProject
    manager_name: str
    lock_files: tuple[Path, ...] = ()


@attrs.define(frozen=True)
class DeclaredDependency:
    """One direct dependency declared in a project manifest.

    Attributes:
        name: Package name as declared in the manifest.
        group: Manifest section key.
        constraint: Raw specifier string from the manifest.
        location_key: Stable identity for planning deduplication.
        resolved_version: Version from the lock file when known.
        installed_version: Version installed in the active environment.
        is_workspace: Whether the entry uses a workspace protocol.
    """

    name: str
    group: str
    constraint: str
    location_key: str
    resolved_version: str | None = None
    installed_version: str | None = None
    is_workspace: bool = False


@attrs.define(frozen=True)
class RegistryVersion:
    """One version reported by a package registry.

    Attributes:
        version: Normalized version string.
        is_prerelease: Whether the version is a prerelease.
        is_yanked: Whether the release is yanked or unavailable.
    """

    version: str
    is_prerelease: bool = False
    is_yanked: bool = False


@attrs.define(frozen=True)
class DependencyVersionChoice:
    """Registry data and defaults for one dependency row.

    Attributes:
        dependency: Declared dependency metadata.
        available_versions: Published versions newest-first.
        latest_stable: Default upgrade target when present.
        lookup_error: Non-fatal registry failure message.
    """

    dependency: DeclaredDependency
    available_versions: tuple[RegistryVersion, ...] = ()
    latest_stable: str | None = None
    lookup_error: str | None = None


@attrs.define(frozen=True)
class DependencySelection:
    """User selection for one dependency row.

    Attributes:
        dependency: Declared dependency metadata.
        target_version: Selected version, or None to skip.
        cycle_index: Index into the UI version cycle state.
    """

    dependency: DeclaredDependency
    target_version: str | None
    cycle_index: int = 0


@attrs.define(frozen=True)
class SourceUpgradePlan:
    """Approved upgrades for one package source.

    Attributes:
        source: Package source metadata.
        selections: User choices for that source.
        manifest_path: Manifest file to update.
        planned_changes: Previewed manifest edits.
    """

    source: PackageSource
    selections: tuple[DependencySelection, ...]
    manifest_path: Path
    planned_changes: tuple[DependencyUpdateChange, ...] = ()


@attrs.define(frozen=True)
class DependencyUpgradePlan:
    """Immutable plan across all approved sources.

    Attributes:
        repo_root: Repository root directory.
        sources: Per-source upgrade plans.
        dry_run: Whether execution must avoid writes.
        install_packages: Whether execution installs into the environment.
    """

    repo_root: Path
    sources: tuple[SourceUpgradePlan, ...]
    dry_run: bool = False
    install_packages: bool = True


@attrs.define
class PluginCommandResult:
    """Outcome from one package-manager subprocess.

    Attributes:
        command: argv executed or planned.
        returncode: Process exit code.
        stdout: Captured standard output.
        stderr: Captured standard error.
    """

    command: list[str] = attrs.Factory(list)
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


@attrs.define
class SourceUpgradeResult:
    """Execution outcome for one package source.

    Attributes:
        source_name: Distlift project name.
        manifest_changes: Direct manifest edits applied.
        lock_files_updated: Lock paths refreshed.
        packages_installed: Environment install commands or package labels.
        warnings: Non-fatal messages.
        rolled_back: Whether snapshots were restored after failure.
    """

    source_name: str
    manifest_changes: list[DependencyUpdateChange] = attrs.Factory(list)
    lock_files_updated: list[Path] = attrs.Factory(list)
    packages_installed: list[str] = attrs.Factory(list)
    warnings: list[str] = attrs.Factory(list)
    rolled_back: bool = False


@attrs.define
class DependencyUpgradeResult:
    """Overall result from an interactive upgrade run.

    Attributes:
        success: Whether all requested sources completed.
        source_results: Per-source execution detail.
        error: Top-level failure message when ``success`` is False.
    """

    success: bool
    source_results: list[SourceUpgradeResult] = attrs.Factory(list)
    error: str | None = None
