"""Reusable dependency updater plugin backed by a TOML rule file."""

from __future__ import annotations

from pathlib import Path

import attrs

from distlift.config.loader import (
    dependency_updates_from_mapping,
    load_toml_config,
)
from distlift.config.models import DependencyUpdatesConfig, ReleaseMode
from distlift.dependencies.models import (
    DependencyUpdateRequest,
    DependencyUpdateResult,
)
from distlift.dependencies.projects import (
    dependency_projects_from_config,
    filter_receive_enabled_dependency_projects,
    filter_trigger_enabled_released_versions,
)
from distlift.dependencies.service import (
    matching_released_version,
    select_projects_for_rule,
    update_projects_for_released_versions,
)
from distlift.plugins.base import DependencyUpdaterPlugin
from distlift.plugins.registry import PluginRegistry


@attrs.define
class ConfiguredDependencyUpdaterPlugin(DependencyUpdaterPlugin):
    """Dependency update plugin backed by a small TOML config file.

    Attributes:
        name: Plugin name exposed in ``distlift plugins list``.
        version: Plugin version string.
        config_path: TOML file containing dependency update rules.
        _du_config: Parsed dependency update settings from the TOML file.
    """

    name: str
    version: str
    config_path: Path

    du_config: DependencyUpdatesConfig = attrs.field(repr=False)

    @classmethod
    def from_file(
        cls,
        name: str,
        version: str,
        config_path: Path,
    ) -> ConfiguredDependencyUpdaterPlugin:
        """Create a plugin that reads dependency update rules from a file.

        Args:
            name: Plugin display name.
            version: Plugin version string.
            config_path: Path to the dependency-updater TOML file.
        """
        data = load_toml_config(config_path)
        du = dependency_updates_from_mapping(data.get("dependency_updates"))

        return cls(
            name=name,
            version=version,
            config_path=config_path,
            du_config=du,
        )

    def get_name(self) -> str:
        """Return the unique plugin name."""
        return self.name

    def get_version(self) -> str:
        """Return the plugin version string."""
        return self.version

    def get_updater_name(self) -> str:
        """Return the unique dependency updater name."""
        return self.name

    def register(self, registry: PluginRegistry) -> None:
        """Register this dependency updater.

        Args:
            registry: Registry receiving the updater binding.
        """
        registry.register_dependency_updater_plugin(self, source="entry-point")

    def update_dependencies(
        self, request: DependencyUpdateRequest
    ) -> DependencyUpdateResult:
        """Apply configured dependency update rules for this release.

        Args:
            request: Dependency update inputs for this run.
        """
        if not self.du_config.enabled and not self.du_config.rules:
            return DependencyUpdateResult(updater_name=self.name)

        from distlift.app import DistliftApplication

        app = DistliftApplication()
        registry = app.load_plugins(request.config)
        projects = dependency_projects_from_config(
            request.repo_root, request.config, registry
        )

        if request.config.mode == ReleaseMode.MONOREPO:
            projects = filter_receive_enabled_dependency_projects(
                projects, request.config.monorepo.packages
            )

        released = list(request.released_versions)

        if request.config.mode == ReleaseMode.MONOREPO:
            released = filter_trigger_enabled_released_versions(
                released, request.config.monorepo.packages
            )

        all_changes = []
        warnings: list[str] = []
        seen: set[tuple[str, str, str]] = set()
        du = self.du_config

        for rule in du.rules:
            rv = matching_released_version(released, rule)

            if rv is None:
                continue

            selected = select_projects_for_rule(projects, rule)
            result = update_projects_for_released_versions(
                selected,
                [rv],
                du,
                rule=rule,
                dry_run=request.dry_run,
                seen=seen,
            )
            all_changes.extend(result.changes)
            warnings.extend(result.warnings)

        return DependencyUpdateResult(
            updater_name=self.name,
            changes=all_changes,
            warnings=warnings,
        )
