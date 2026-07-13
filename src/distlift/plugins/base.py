from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from distlift.config.models import ResolvedConfig
    from distlift.dependencies.models import (
        DependencyProject,
        DependencyUpdateChange,
        DependencyUpdateRequest,
        DependencyUpdateResult,
    )
    from distlift.dependencies.upgrade_models import (
        DeclaredDependency,
        DependencySelection,
        PackageSource,
        PluginCommandResult,
        RegistryVersion,
    )
    from distlift.plugins.registry import PluginRegistry


class DistliftPlugin(ABC):
    """Base interface every distlift plugin must satisfy.

    Attributes:
        (none; subclasses implement the abstract API.)
    """

    @abstractmethod
    def get_name(self) -> str:
        """Return the unique plugin name."""

    @abstractmethod
    def get_version(self) -> str:
        """Return the plugin version string."""

    @abstractmethod
    def register(self, registry: PluginRegistry) -> None:
        """Register plugin capabilities into the registry.

        Args:
            registry: Active plugin registry to register into.
        """


class LanguagePlugin(DistliftPlugin):
    """Plugin that provides language detection and project adaptation.

    Attributes:
        (none; language plugins register a ProjectAdapter via the registry.)
    """

    @abstractmethod
    def get_language(self) -> str:
        """Return the language id this plugin handles (e.g. ``python``)."""


class ManifestPlugin(DistliftPlugin):
    """Plugin that reads and writes a specific manifest format.

    Attributes:
        (none; manifest plugins register readers/writers via the registry.)
    """

    @abstractmethod
    def get_kind(self) -> str:
        """Return manifest kind (e.g. ``pyproject`` or ``package_json``)."""


class VersionSourcePlugin(DistliftPlugin):
    """Plugin that resolves the current version from a non-standard source.

    Attributes:
        (none; version source plugins register resolvers via the registry.)
    """

    @abstractmethod
    def get_source_name(self) -> str:
        """Return the version source identifier."""


class PublishPlugin(DistliftPlugin):
    """Plugin that builds and publishes package artifacts.

    Attributes:
        (none; publish plugins register publishers via the registry.)
    """

    @abstractmethod
    def get_language(self) -> str:
        """Return the language this publisher handles."""


class GitBackendPlugin(DistliftPlugin):
    """Plugin that provides Git repository operations.

    Attributes:
        (none; a single Git backend replaces subprocess usage when registered.)
    """


class DependencyUpdaterPlugin(DistliftPlugin):
    """Plugin that updates dependent project manifests during releases.

    Attributes:
        (none; concrete plugins implement the update method.)
    """

    @abstractmethod
    def get_updater_name(self) -> str:
        """Return the unique dependency updater name."""

    @abstractmethod
    def update_dependencies(
        self, request: DependencyUpdateRequest
    ) -> DependencyUpdateResult:
        """Update or preview dependent package dependency declarations."""


class ChangelogPlugin(DistliftPlugin):
    """Plugin that formats changelog documents for releases.

    Attributes:
        (none; a single changelog plugin formats changelog Markdown.)
    """

    @abstractmethod
    def get_format(self) -> str:
        """Return the changelog format identifier (``keep-a-changelog``)."""


class PackageManagerPlugin(DistliftPlugin):
    """Plugin that inventories and upgrades third-party dependencies.

    Attributes:
        (none; concrete plugins implement manager-specific behavior.)
    """

    @abstractmethod
    def get_manager_name(self) -> str:
        """Return stable manager id (``pip``, ``npm``, ``pnpm``, ``yarn``)."""

    @abstractmethod
    def detect_source(
        self,
        project: DependencyProject,
        *,
        override_name: str | None = None,
    ) -> PackageSource | None:
        """Return source metadata when this plugin owns the project.

        Args:
            project: Candidate dependency project.
            override_name: Optional forced manager name from CLI or config.
        """

    @abstractmethod
    def list_dependencies(
        self, source: PackageSource
    ) -> list[DeclaredDependency]:
        """Enumerate direct dependencies from manifest and lock hints.

        Args:
            source: Package source to inspect.
        """

    def read_lock_versions(self, source: PackageSource) -> dict[str, str]:
        """Return direct dependency versions resolved in lock files.

        Args:
            source: Package source whose lock files may be read.
        """
        return {}

    def read_installed_versions(self, source: PackageSource) -> dict[str, str]:
        """Return versions installed in the active package environment.

        Args:
            source: Package source whose environment should be inspected.
        """
        return {}

    @abstractmethod
    def fetch_available_versions(
        self,
        dependency_name: str,
        source: PackageSource,
        *,
        timeout_seconds: int,
    ) -> list[RegistryVersion]:
        """Return published versions for one dependency newest-first.

        Args:
            dependency_name: Registry package name.
            source: Package source providing registry context.
            timeout_seconds: Subprocess timeout for registry queries.
        """

    @abstractmethod
    def format_target_specifier(
        self,
        dependency: DeclaredDependency,
        target_version: str,
        config: ResolvedConfig,
    ) -> str:
        """Build the new manifest specifier for one selected version.

        Args:
            dependency: Declared dependency metadata.
            target_version: User-selected target version.
            config: Effective merged configuration.
        """

    @abstractmethod
    def apply_manifest_updates(
        self,
        source: PackageSource,
        selections: list[DependencySelection],
        config: ResolvedConfig,
        *,
        dry_run: bool,
    ) -> list[DependencyUpdateChange]:
        """Write or preview manifest edits for selected dependencies.

        Args:
            source: Package source being updated.
            selections: User selections with non-None target versions.
            config: Effective merged configuration.
            dry_run: When True, compute changes without writing files.
        """

    @abstractmethod
    def refresh_lock_files(
        self,
        source: PackageSource,
        *,
        dry_run: bool,
        timeout_seconds: int,
    ) -> list[Path]:
        """Regenerate lock files after manifest changes.

        Args:
            source: Package source whose locks should refresh.
            dry_run: When True, report paths without running commands.
            timeout_seconds: Subprocess timeout for lock refresh.
        """

    @abstractmethod
    def install_packages(
        self,
        source: PackageSource,
        selections: list[DependencySelection],
        config: ResolvedConfig,
        *,
        dry_run: bool,
        timeout_seconds: int,
    ) -> list[PluginCommandResult]:
        """Install upgraded packages into the active environment.

        Args:
            source: Package source whose environment should update.
            selections: User selections with non-None target versions.
            config: Effective merged configuration.
            dry_run: When True, preview commands without executing them.
            timeout_seconds: Subprocess timeout for install commands.
        """

    @abstractmethod
    def verify_upgrades(
        self,
        source: PackageSource,
        selections: list[DependencySelection],
        config: ResolvedConfig,
    ) -> list[str]:
        """Return verification errors; empty list means success.

        Args:
            source: Package source that was updated.
            selections: Applied selections with target versions.
            config: Effective merged configuration.
        """
