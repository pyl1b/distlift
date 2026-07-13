"""Built-in pip package manager plugin."""

from __future__ import annotations

import sys
from pathlib import Path

from distlift.config.models import Language, ResolvedConfig
from distlift.dependencies.inventory import list_python_dependencies
from distlift.dependencies.models import (
    DependencyProject,
    DependencyUpdateChange,
)
from distlift.dependencies.python import (
    find_python_dependency_specs,
    update_python_dependency,
)
from distlift.dependencies.registry_query import fetch_pip_versions
from distlift.dependencies.upgrade_models import (
    DeclaredDependency,
    DependencySelection,
    PackageSource,
    PluginCommandResult,
    RegistryVersion,
)
from distlift.package_managers.base import (
    BuiltinPackageManagerPlugin,
    preserve_python_specifier_style,
    python_pip_requirement,
    run_command,
    verify_installed_package_versions,
)
from distlift.package_managers.installed import read_python_installed_versions


class PipPackageManagerPlugin(BuiltinPackageManagerPlugin):
    """Upgrade PEP 621 dependencies using pip registry queries.

    Attributes:
        _manager_name: Stable manager id ``pip``.
    """

    _manager_name = "pip"

    def detect_source(
        self,
        project: DependencyProject,
        *,
        override_name: str | None = None,
    ) -> PackageSource | None:
        """Return a pip source when the project is Python-based.

        Args:
            project: Candidate dependency project.
            override_name: Optional forced manager name.
        """
        if override_name is not None and override_name != self._manager_name:
            return None

        if override_name is None and project.language != Language.PYTHON:
            return None

        manifest = project.manifest_path

        if not manifest.is_file():
            return None

        return PackageSource(
            project=project,
            manager_name=self._manager_name,
            lock_files=(),
        )

    def list_dependencies(
        self, source: PackageSource
    ) -> list[DeclaredDependency]:
        """List dependencies declared in ``pyproject.toml``.

        Args:
            source: Package source to inspect.
        """
        return list_python_dependencies(source.project.manifest_path)

    def read_installed_versions(self, source: PackageSource) -> dict[str, str]:
        """Read versions installed in the active Python environment.

        Args:
            source: Package source whose dependencies should be inspected.
        """
        dependency_names = [
            dependency.name for dependency in self.list_dependencies(source)
        ]
        return read_python_installed_versions(dependency_names)

    def fetch_available_versions(
        self,
        dependency_name: str,
        source: PackageSource,
        *,
        timeout_seconds: int,
    ) -> list[RegistryVersion]:
        """Query PyPI versions through the active pip interpreter.

        Args:
            dependency_name: PyPI distribution name.
            source: Package source providing registry context.
            timeout_seconds: Subprocess timeout in seconds.
        """
        return fetch_pip_versions(
            dependency_name,
            timeout_seconds=timeout_seconds,
        )

    def format_target_specifier(
        self,
        dependency: DeclaredDependency,
        target_version: str,
        config: ResolvedConfig,
    ) -> str:
        """Preserve Python specifier style when formatting the target.

        Args:
            dependency: Declared dependency metadata.
            target_version: Selected target version.
            config: Effective merged configuration.
        """
        return preserve_python_specifier_style(
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
        """Update selected Python dependencies in ``pyproject.toml``.

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
            template = _template_for_specifier(
                new_spec, selection.target_version
            )
            pairs = update_python_dependency(
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
        """Report that pip has no standard project lock file to refresh.

        Args:
            source: Package source whose locks would refresh.
            dry_run: When True, skip subprocess execution.
            timeout_seconds: Unused for pip; kept for interface parity.
        """
        return []

    def install_packages(
        self,
        source: PackageSource,
        selections: list[DependencySelection],
        config: ResolvedConfig,
        *,
        dry_run: bool,
        timeout_seconds: int,
    ) -> list[PluginCommandResult]:
        """Install selected Python packages into the active environment.

        Args:
            source: Package source whose environment should update.
            selections: User selections with target versions.
            config: Effective merged configuration.
            dry_run: When True, preview commands without executing them.
            timeout_seconds: Subprocess timeout in seconds.
        """
        results: list[PluginCommandResult] = []

        for selection in selections:
            if selection.target_version is None:
                continue

            specifier = self.format_target_specifier(
                selection.dependency,
                selection.target_version,
                config,
            )
            requirement = python_pip_requirement(
                selection.dependency.name,
                specifier,
            )
            cmd = [sys.executable, "-m", "pip", "install", requirement]
            result = run_command(
                cmd,
                cwd=source.project.root,
                dry_run=dry_run,
                timeout_seconds=timeout_seconds,
                mutating=True,
            )
            results.append(result)

            if result.returncode != 0:
                raise RuntimeError(result.stderr or result.stdout)

        return results

    def verify_upgrades(
        self,
        source: PackageSource,
        selections: list[DependencySelection],
        config: ResolvedConfig,
    ) -> list[str]:
        """Verify selected specifiers appear in the manifest.

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
            locations = find_python_dependency_specs(
                path, selection.dependency.name
            )

            if not locations:
                errors.append(
                    f"{selection.dependency.name} missing from {path}"
                )
                continue

            if (
                expected not in locations[0].original
                and selection.target_version not in locations[0].original
            ):
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


def _template_for_specifier(specifier: str, version: str) -> str:
    """Convert an absolute specifier into an update template.

    Args:
        specifier: Fully formatted target specifier.
        version: Selected version embedded in the specifier.
    """
    if version in specifier:
        return specifier.replace(version, "{version}")

    return specifier
