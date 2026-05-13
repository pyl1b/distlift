from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from distlift.plugins.registry import PluginRegistry


class DistliftPlugin(ABC):
    """Base interface every distlift plugin must satisfy."""

    @abstractmethod
    def get_name(self) -> str:
        """Return the unique plugin name."""

    @abstractmethod
    def get_version(self) -> str:
        """Return the plugin version string."""

    @abstractmethod
    def register(self, registry: PluginRegistry) -> None:
        """Register plugin capabilities into the registry."""


class LanguagePlugin(DistliftPlugin):
    """Plugin that provides language detection and project adaptation."""

    @abstractmethod
    def get_language(self) -> str:
        """Return the language identifier this plugin handles (e.g. 'python')."""


class ManifestPlugin(DistliftPlugin):
    """Plugin that reads and writes a specific manifest format."""

    @abstractmethod
    def get_kind(self) -> str:
        """Return the manifest kind identifier (e.g. 'pyproject', 'package_json')."""


class VersionSourcePlugin(DistliftPlugin):
    """Plugin that resolves the current version from a non-standard source."""

    @abstractmethod
    def get_source_name(self) -> str:
        """Return the version source identifier."""


class PublishPlugin(DistliftPlugin):
    """Plugin that builds and publishes package artifacts."""

    @abstractmethod
    def get_language(self) -> str:
        """Return the language this publisher handles."""


class GitBackendPlugin(DistliftPlugin):
    """Plugin that provides Git repository operations."""
