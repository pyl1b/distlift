"""Models for dependency autoupdate execution and plugins."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import attrs

from distlift.config.models import Language

if TYPE_CHECKING:
    from distlift.config.models import ResolvedConfig
    from distlift.release.models import ReleasePlan


@attrs.define(frozen=True)
class ReleasedProjectVersion:
    """Identity and version of one package included in a release plan.

    Attributes:
        package_name: Distlift monorepo package name, if available.
        dependency_name: Name used by package managers in dependencies.
        version: New version string.
        language: Language of the released package.
        root: Package root directory.
        manifest_path: Manifest file path.
    """

    package_name: str | None
    dependency_name: str
    version: str
    language: Language
    root: Path
    manifest_path: Path


@attrs.define(frozen=True)
class DependencyProject:
    """Project whose dependency declarations can be inspected and updated.

    Attributes:
        name: Distlift monorepo package name.
        dependency_name: Package-manager name declared by the manifest.
        language: Project language.
        root: Project root directory.
        manifest_path: Manifest file path.
    """

    name: str
    dependency_name: str
    language: Language
    root: Path
    manifest_path: Path


@attrs.define(frozen=True)
class DependencyUpdateChange:
    """One dependency declaration changed or planned for change.

    Attributes:
        project_name: Dependent project being updated.
        dependency_name: Released dependency whose specifier changed.
        manifest_path: Manifest file containing the dependency declaration.
        old_specifier: Original version/range text.
        new_specifier: New version/range text.
    """

    project_name: str
    dependency_name: str
    manifest_path: Path
    old_specifier: str
    new_specifier: str


@attrs.define
class DependencyUpdateResult:
    """Summary returned by one dependency updater.

    Attributes:
        updater_name: Plugin or built-in updater name.
        changes: Dependency declarations changed or planned.
        warnings: Non-fatal problems, such as a selected project with no
            matching dependency.
    """

    updater_name: str
    changes: list[DependencyUpdateChange] = attrs.Factory(list)
    warnings: list[str] = attrs.Factory(list)


@attrs.define(frozen=True)
class DependencyUpdateRequest:
    """Inputs passed to dependency update plugins.

    Attributes:
        repo_root: Release repository root.
        config: Effective release repository configuration.
        plan: Active release plan, or None for the standalone command.
        released_versions: Released package identities and next versions.
        dry_run: When True, report changes without writing files.
        run_source: Either ``release`` or ``command``.
    """

    repo_root: Path
    config: ResolvedConfig
    plan: ReleasePlan | None
    released_versions: list[ReleasedProjectVersion]
    dry_run: bool
    run_source: str = "release"
