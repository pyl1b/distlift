"""Built-in yarn package manager plugin."""

from __future__ import annotations

from pathlib import Path

from distlift.config.models import Language, ResolvedConfig
from distlift.dependencies.models import DependencyProject
from distlift.dependencies.registry_query import fetch_yarn_versions
from distlift.dependencies.upgrade_models import (
    DependencySelection,
    PackageSource,
    PluginCommandResult,
    RegistryVersion,
)
from distlift.package_managers.base import (
    package_manager_field,
    run_command,
)
from distlift.package_managers.npm import NpmPackageManagerPlugin


class YarnPackageManagerPlugin(NpmPackageManagerPlugin):
    """Upgrade dependencies using yarn and refresh ``yarn.lock``.

    Attributes:
        _manager_name: Stable manager id ``yarn``.
    """

    _manager_name = "yarn"

    def detect_source(
        self,
        project: DependencyProject,
        *,
        override_name: str | None = None,
    ) -> PackageSource | None:
        """Return a yarn source when yarn markers are present.

        Args:
            project: Candidate dependency project.
            override_name: Optional forced manager name.
        """
        if not self._project_matches_language(
            project, Language.JAVASCRIPT, override_name=override_name
        ):
            return None

        root = project.root
        lock_file = root / "yarn.lock"
        pm_field = package_manager_field(root)
        pm_manager = None

        if pm_field:
            from distlift.package_managers.base import (
                manager_from_package_manager_field,
            )

            pm_manager = manager_from_package_manager_field(pm_field)

        if override_name is None:
            if pm_manager not in (None, self._manager_name):
                return None

            if not lock_file.is_file() and pm_manager is None:
                return None

        lock_files = (lock_file,) if lock_file.is_file() else ()

        return PackageSource(
            project=project,
            manager_name=self._manager_name,
            lock_files=lock_files,
        )

    def fetch_available_versions(
        self,
        dependency_name: str,
        source: PackageSource,
        *,
        timeout_seconds: int,
    ) -> list[RegistryVersion]:
        """Query registry versions through yarn or npm fallback.

        Args:
            dependency_name: npm package name.
            source: Package source providing registry context.
            timeout_seconds: Subprocess timeout in seconds.
        """
        return fetch_yarn_versions(
            dependency_name,
            timeout_seconds=timeout_seconds,
        )

    def refresh_lock_files(
        self,
        source: PackageSource,
        *,
        dry_run: bool,
        timeout_seconds: int,
    ) -> list[Path]:
        """Refresh ``yarn.lock`` using the safest lockfile-only mode available.

        Args:
            source: Package source whose lock file should refresh.
            dry_run: When True, skip subprocess execution.
            timeout_seconds: Subprocess timeout in seconds.
        """
        lock_file = source.project.root / "yarn.lock"

        if not lock_file.is_file():
            return []

        if (source.project.root / ".yarnrc.yml").is_file():
            cmd = ["yarn", "install", "--mode", "update-lockfile"]
        else:
            cmd = ["yarn", "install", "--ignore-scripts"]

        result = run_command(
            cmd,
            cwd=source.project.root,
            dry_run=dry_run,
            timeout_seconds=timeout_seconds,
            mutating=True,
        )

        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout)

        return [lock_file] if not dry_run else []

    def install_packages(
        self,
        source: PackageSource,
        selections: list[DependencySelection],
        config: ResolvedConfig,
        *,
        dry_run: bool,
        timeout_seconds: int,
    ) -> list[PluginCommandResult]:
        """Install yarn dependencies into ``node_modules``.

        Args:
            source: Package source whose environment should update.
            selections: User selections with target versions.
            config: Effective merged configuration.
            dry_run: When True, preview commands without executing them.
            timeout_seconds: Subprocess timeout in seconds.
        """
        active = [
            selection
            for selection in selections
            if selection.target_version is not None
        ]

        if not active:
            return []

        if (source.project.root / ".yarnrc.yml").is_file():
            cmd = ["yarn", "install"]
        else:
            cmd = ["yarn", "install", "--ignore-scripts"]

        result = run_command(
            cmd,
            cwd=source.project.root,
            dry_run=dry_run,
            timeout_seconds=timeout_seconds,
            mutating=True,
        )

        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout)

        return [result]
