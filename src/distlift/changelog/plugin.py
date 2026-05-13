"""Built-in Keep a Changelog plugin registration."""

from __future__ import annotations

from distlift.plugins.base import ChangelogPlugin
from distlift.plugins.registry import PluginRegistry


class KeepAChangelogBuiltinPlugin(ChangelogPlugin):
    """Register the default Keep a Changelog formatter hook."""

    def get_name(self) -> str:
        """Return the stable identifier for this changelog plugin."""
        return "builtin-keep-a-changelog"

    def get_version(self) -> str:
        """Return a semver-like plugin version string."""
        return "1.0.0"

    def get_format(self) -> str:
        """Return the changelog format key understood by distlift."""
        return "keep-a-changelog"

    def register(self, registry: PluginRegistry) -> None:
        """Attach this changelog plugin to ``registry``.

        Args:
            registry: Active plugin registry for the current distlift run.
        """
        registry.register_changelog_plugin(self, source="builtin")
