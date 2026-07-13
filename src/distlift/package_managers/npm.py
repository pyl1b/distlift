"""Built-in npm package manager plugin."""

from __future__ import annotations

from pathlib import Path

from distlift.config.models import Language, ResolvedConfig
from distlift.dependencies.inventory import list_javascript_dependencies
from distlift.dependencies.javascript import (
    find_javascript_dependency_specs,
    update_javascript_dependency,
)
from distlift.dependencies.models import (
    DependencyProject,
    DependencyUpdateChange,
)
from distlift.dependencies.registry_query import fetch_npm_versions
from distlift.dependencies.upgrade_models import (
    DeclaredDependency,
    DependencySelection,
    PackageSource,
    PluginCommandResult,
    RegistryVersion,
)
from distlift.package_managers.base import (
    BuiltinPackageManagerPlugin,
    package_manager_field,
    preserve_javascript_specifier_style,
    read_npm_lock_versions,
    run_command,
    verify_installed_package_versions,
)
from distlift.package_managers.installed import (
    read_node_modules_installed_versions,
)


class NpmPackageManagerPlugin(BuiltinPackageManagerPlugin):
    """Upgrade npm dependencies and refresh ``package-lock.json``.

    Attributes:
        _manager_name: Stable manager id ``npm``.
    """

    _manager_name = "npm"

    def detect_source(
        self,
        project: DependencyProject,
        *,
        override_name: str | None = None,
    ) -> PackageSource | None:
        """Return an npm source when npm markers are present.

        Args:
            project: Candidate dependency project.
            override_name: Optional forced manager name.
        """
        if not self._project_matches_language(
            project, Language.JAVASCRIPT, override_name=override_name
        ):
            return None

        root = project.root
        lock_file = root / "package-lock.json"
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
                if project.language == Language.JAVASCRIPT:
                    return PackageSource(
                        project=project,
                        manager_name=self._manager_name,
                        lock_files=(),
                    )
                return None

        lock_files = (lock_file,) if lock_file.is_file() else ()

        return PackageSource(
            project=project,
            manager_name=self._manager_name,
            lock_files=lock_files,
        )

    def list_dependencies(
        self, source: PackageSource
    ) -> list[DeclaredDependency]:
        """List dependencies declared in ``package.json``.

        Args:
            source: Package source to inspect.
        """
        return list_javascript_dependencies(source.project.manifest_path)

    def read_lock_versions(self, source: PackageSource) -> dict[str, str]:
        """Read resolved versions from ``package-lock.json``.

        Args:
            source: Package source whose lock file may be read.
        """
        versions: dict[str, str] = {}

        for lock_path in source.lock_files:
            versions.update(read_npm_lock_versions(lock_path))

        return versions

    def read_installed_versions(self, source: PackageSource) -> dict[str, str]:
        """Read versions installed under ``node_modules``.

        Args:
            source: Package source whose dependencies should be inspected.
        """
        dependency_names = [
            dependency.name for dependency in self.list_dependencies(source)
        ]
        return read_node_modules_installed_versions(
            source.project.root,
            dependency_names,
        )

    def fetch_available_versions(
        self,
        dependency_name: str,
        source: PackageSource,
        *,
        timeout_seconds: int,
    ) -> list[RegistryVersion]:
        """Query npm registry versions for one package.

        Args:
            dependency_name: npm package name.
            source: Package source providing registry context.
            timeout_seconds: Subprocess timeout in seconds.
        """
        return fetch_npm_versions(
            dependency_name,
            timeout_seconds=timeout_seconds,
        )

    def format_target_specifier(
        self,
        dependency: DeclaredDependency,
        target_version: str,
        config: ResolvedConfig,
    ) -> str:
        """Preserve JavaScript range style when formatting the target.

        Args:
            dependency: Declared dependency metadata.
            target_version: Selected target version.
            config: Effective merged configuration.
        """
        return preserve_javascript_specifier_style(
            dependency.constraint,
            target_version,
            config,
        )

    def apply_manifest_updates(
        self,
        source: PackageSource,
        selections: list[DependencySelection],
        config: ResolvedConfig,
        *,
        dry_run: bool,
    ) -> list[DependencyUpdateChange]:
        """Update selected JavaScript dependencies in ``package.json``.

        Args:
            source: Package source being updated.
            selections: User selections with target versions.
            config: Effective merged configuration.
            dry_run: When True, compute changes without writing files.
        """
        changes: list[DependencyUpdateChange] = []
        path = source.project.manifest_path

        for selection in selections:
            if selection.target_version is None:
                continue

            new_spec = self.format_target_specifier(
                selection.dependency,
                selection.target_version,
                config,
            )
            template = new_spec.replace(selection.target_version, "{version}")
            pairs = update_javascript_dependency(
                path,
                selection.dependency.name,
                template,
                selection.target_version,
                dry_run=dry_run,
            )

            for old_spec, new_value in pairs:
                changes.append(
                    DependencyUpdateChange(
                        project_name=source.project.name,
                        dependency_name=selection.dependency.name,
                        manifest_path=path,
                        old_specifier=old_spec,
                        new_specifier=new_value,
                    )
                )

        return changes

    def refresh_lock_files(
        self,
        source: PackageSource,
        *,
        dry_run: bool,
        timeout_seconds: int,
    ) -> list[Path]:
        """Refresh ``package-lock.json`` without running lifecycle scripts.

        Args:
            source: Package source whose lock file should refresh.
            dry_run: When True, skip subprocess execution.
            timeout_seconds: Subprocess timeout in seconds.
        """
        lock_file = source.project.root / "package-lock.json"

        if not lock_file.is_file():
            return []

        cmd = ["npm", "install", "--package-lock-only", "--ignore-scripts"]
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
        """Install npm dependencies into ``node_modules``.

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

        cmd = ["npm", "install", "--ignore-scripts"]
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

    def verify_upgrades(
        self,
        source: PackageSource,
        selections: list[DependencySelection],
        config: ResolvedConfig,
    ) -> list[str]:
        """Verify selected specifiers appear in ``package.json``.

        Args:
            source: Package source that was updated.
            selections: Applied selections with target versions.
            config: Effective merged configuration.
        """
        errors: list[str] = []
        path = source.project.manifest_path

        for selection in selections:
            if selection.target_version is None:
                continue

            expected = self.format_target_specifier(
                selection.dependency,
                selection.target_version,
                config,
            )
            locations = find_javascript_dependency_specs(
                path,
                selection.dependency.name,
            )

            if not locations:
                errors.append(
                    f"{selection.dependency.name} missing from {path}"
                )
                continue

            if expected not in locations[0].original:
                errors.append(
                    f"{selection.dependency.name} not updated to {expected}"
                )

        if config.dependency_upgrades.install_packages:
            installed_versions = self.read_installed_versions(source)
            errors.extend(
                verify_installed_package_versions(
                    installed_versions,
                    selections,
                )
            )

        return errors
