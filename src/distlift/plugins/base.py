from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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


class ChangelogPlugin(DistliftPlugin):
    """Plugin that formats changelog documents for releases.

    Attributes:
        (none; a single changelog plugin formats changelog Markdown.)
    """

    @abstractmethod
    def get_format(self) -> str:
        """Return the changelog format identifier (``keep-a-changelog``)."""
