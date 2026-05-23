"""Resolve dependency project identities from plans and configuration."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from distlift.config.models import (
    Language,
    ManagedPackageConfig,
    ReleaseMode,
    ResolvedConfig,
)
from distlift.dependencies.models import (
    DependencyProject,
    ReleasedProjectVersion,
)
from distlift.manifests.handler import kind_for_language
from distlift.manifests.package_json_file import (
    get_package_name,
    read_package_json,
)
from distlift.manifests.pyproject_file import get_project_name, read_pyproject
from distlift.monorepo.discovery import (
    load_managed_packages,
)
from distlift.release.models import ReleasePlan, ReleaseTarget

if TYPE_CHECKING:
    from distlift.app import DistliftApplication
    from distlift.plugins.registry import PluginRegistry


def normalize_python_dependency_name(name: str) -> str:
    """Normalize a Python distribution name for dependency matching.

    Args:
        name: Raw dependency or project name string.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def released_versions_from_plan(
    plan: ReleasePlan,
) -> list[ReleasedProjectVersion]:
    """Build released version records from a release plan.

    Args:
        plan: Computed release plan with next versions per package.
    """
    released: list[ReleasedProjectVersion] = []

    for pkg_plan in plan.packages:
        target = pkg_plan.target
        version_str = str(pkg_plan.resolved_version.next)
        dep_name = _dependency_name_for_target(target)

        released.append(
            ReleasedProjectVersion(
                package_name=target.package_name,
                dependency_name=dep_name,
                version=version_str,
                language=target.language,
                root=target.root,
                manifest_path=target.manifest_path,
            )
        )

    return released


def dependency_project_from_target(target: ReleaseTarget) -> DependencyProject:
    """Convert a release target into a dependency project descriptor.

    Args:
        target: Release target with manifest and package metadata.
    """
    dep_name = _dependency_name_for_target(target)
    name = target.package_name or dep_name

    return DependencyProject(
        name=name,
        dependency_name=dep_name,
        language=target.language,
        root=target.root,
        manifest_path=target.manifest_path,
    )


def dependency_projects_from_target(
    target: ReleaseTarget,
) -> list[DependencyProject]:
    """Convert a release target into one or more dependency project records.

    Args:
        target: Release target with manifest and version-file metadata.
    """
    if not target.version_files:
        return [dependency_project_from_target(target)]

    projects: list[DependencyProject] = []
    multiple_files = len(target.version_files) > 1

    for vf in target.version_files:
        language = _language_for_manifest_kind(vf.kind)

        if language is None:
            continue

        dep_name = manifest_dependency_name(vf.path, language)

        if not dep_name:
            continue

        if target.package_name:
            name = target.package_name
        elif multiple_files:
            name = f"{target.root.name}/{vf.path.parent.name}"
        else:
            name = target.root.name

        projects.append(
            DependencyProject(
                name=name,
                dependency_name=dep_name,
                language=language,
                root=vf.path.parent,
                manifest_path=vf.path,
            )
        )

    return projects


def dependency_projects_from_config(
    repo_root: Path,
    config: ResolvedConfig,
    registry: PluginRegistry,
) -> list[DependencyProject]:
    """List dependency projects declared in the current monorepo config.

    Args:
        repo_root: Repository root for path resolution.
        config: Effective merged configuration.
        registry: Plugin registry (reserved for future wiring).
    """
    from distlift.release.monorepo import discover_managed_targets
    from distlift.release.simple import prepare_simple_target

    if config.mode == ReleaseMode.MONOREPO or config.monorepo.packages:
        packages = load_managed_packages(config)
        pairs = discover_managed_targets(packages, repo_root, config, registry)

        projects: list[DependencyProject] = []

        for target, _ in pairs:
            projects.extend(dependency_projects_from_target(target))

        return projects

    target, _ = prepare_simple_target(repo_root, config, registry)
    return dependency_projects_from_target(target)


def load_external_monorepo_projects(
    repo_root: Path,
    external_root: Path,
    config_paths: list[Path],
    application: DistliftApplication,
) -> list[DependencyProject]:
    """Load dependency projects from another distlift repository.

    Args:
        repo_root: Release repository root for caller context.
        external_root: Root directory of the external distlift repository.
        config_paths: Optional extra config file paths for that repo.
        application: Application facade used to load config and plugins.
    """
    resolved_external = external_root.resolve()

    config = application.load_effective_config(
        resolved_external,
        config_paths or None,
    )

    from distlift.config.validators import validate_resolved_config

    validate_resolved_config(config)

    registry = application.load_plugins(config)

    return dependency_projects_from_config(resolved_external, config, registry)


def dependency_updates_trigger_enabled_for_package(
    pkg: ManagedPackageConfig,
) -> bool:
    """Return whether releasing this package may trigger dependency updates.

    Args:
        pkg: Managed package configuration row.
    """
    return pkg.dependency_updates_trigger_enabled


def dependency_updates_receive_enabled_for_package(
    pkg: ManagedPackageConfig,
) -> bool:
    """Return whether this package may receive dependency declaration updates.

    Args:
        pkg: Managed package configuration row.
    """
    return pkg.dependency_updates_receive_enabled


def filter_trigger_enabled_released_versions(
    released_versions: list[ReleasedProjectVersion],
    packages: list[ManagedPackageConfig],
) -> list[ReleasedProjectVersion]:
    """Keep only released versions whose package may trigger autoupdates.

    Args:
        released_versions: Candidate released package versions.
        packages: Monorepo package declarations with per-package flags.
    """
    by_name = {p.name: p for p in packages}

    filtered: list[ReleasedProjectVersion] = []

    for rv in released_versions:
        pkg_name = rv.package_name

        if pkg_name is None:
            filtered.append(rv)
            continue

        pkg = by_name.get(pkg_name)

        if pkg is None or dependency_updates_trigger_enabled_for_package(pkg):
            filtered.append(rv)

    return filtered


def filter_receive_enabled_dependency_projects(
    projects: list[DependencyProject],
    packages: list[ManagedPackageConfig],
) -> list[DependencyProject]:
    """Keep only projects that may receive dependency declaration updates.

    Args:
        projects: Candidate dependent projects.
        packages: Monorepo package declarations with per-package flags.
    """
    by_name = {p.name: p for p in packages}

    filtered: list[DependencyProject] = []

    for proj in projects:
        pkg = by_name.get(proj.name)

        if pkg is None or dependency_updates_receive_enabled_for_package(pkg):
            filtered.append(proj)

    return filtered


def _dependency_name_for_target(target: ReleaseTarget) -> str:
    """Resolve the package-manager dependency name for a target.

    Args:
        target: Release target with manifest path and optional package name.
    """
    if target.language == Language.PYTHON:
        data = read_pyproject(target.manifest_path)
        manifest_name = get_project_name(data)

        if manifest_name:
            return manifest_name

    if target.language == Language.JAVASCRIPT:
        data = read_package_json(target.manifest_path)
        manifest_name = get_package_name(data)

        if manifest_name:
            return manifest_name

    if target.package_name:
        return target.package_name

    return target.root.name


def manifest_dependency_name(
    manifest_path: Path, language: Language
) -> str | None:
    """Read the dependency name from a manifest file when possible.

    Args:
        manifest_path: Path to pyproject.toml or package.json.
        language: Project language selector.
    """
    if language == Language.PYTHON:
        data = read_pyproject(manifest_path)
        return get_project_name(data)

    if language == Language.JAVASCRIPT:
        data = read_package_json(manifest_path)
        return get_package_name(data)

    return None


def _language_for_manifest_kind(kind: str) -> Language | None:
    """Return the language enum implied by one manifest kind string.

    Args:
        kind: Manifest kind such as ``pyproject`` or ``package-json``.
    """
    for language in Language:
        if kind_for_language(str(language)) == kind:
            return language

    return None
