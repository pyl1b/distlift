"""Coordinate discovery, loading, and registration of distlift plugins."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import attrs

from distlift.logging_utils import get_logger
from distlift.plugins.base import DistliftPlugin
from distlift.plugins.discovery import (
    discover_entry_point_plugins,
    discover_plugins_from_paths,
    expand_plugin_directories,
)
from distlift.plugins.loader import load_plugins
from distlift.plugins.registry import PluginRegistry

log = get_logger(__name__)


@attrs.define
class PluginLoadRequest:
    """Inputs controlling which plugins are loaded and how they override.

    Attributes:
        plugin_paths: Explicit ``.py`` files or package directories to load.
        plugin_directories: Directories scanned for additional plugins.
        disable_environment_plugins: Skip entry-point discovery when True.
        disable_builtin_plugins: Skip built-in plugins when True.
        allow_plugin_override: Forwarded to ``PluginRegistry.allow_override``.
    """

    plugin_paths: list[Path] = attrs.Factory(list)
    plugin_directories: list[Path] = attrs.Factory(list)
    disable_environment_plugins: bool = False
    disable_builtin_plugins: bool = False
    allow_plugin_override: bool = True


@attrs.define
class PluginManager:
    """Builds a ``PluginRegistry`` from built-ins, environment, and paths.

    Attributes:
        (none; each ``build_registry`` call is independent.)
    """

    def build_registry(self, request: PluginLoadRequest) -> PluginRegistry:
        """Discover and register plugins according to ``request``.

        Args:
            request: Load flags and explicit plugin locations.
        """
        registry = PluginRegistry(allow_override=request.allow_plugin_override)

        all_plugins: list[DistliftPlugin] = []

        if not request.disable_builtin_plugins:
            all_plugins.extend(self.load_builtin_plugins())

        if not request.disable_environment_plugins:
            all_plugins.extend(self.load_environment_plugins())

        if request.plugin_paths:
            all_plugins.extend(
                self.load_explicit_plugins(request.plugin_paths)
            )

        if request.plugin_directories:
            candidates = expand_plugin_directories(request.plugin_directories)
            all_plugins.extend(load_plugins(candidates))

        for plugin in all_plugins:
            try:
                plugin.register(registry)
                log.debug("Registered plugin: %s", plugin.get_name())
            except Exception as exc:
                log.warning(
                    "Plugin '%s' failed to register: %s",
                    plugin.get_name(),
                    exc,
                    exc_info=True,
                )

        return registry

    def load_builtin_plugins(self) -> list[DistliftPlugin]:
        """Return built-in plugin instances (Git, Python, JavaScript)."""
        from distlift.plugins.builtins import build_builtin_plugins

        return build_builtin_plugins()

    def load_environment_plugins(self) -> list[DistliftPlugin]:
        """Load plugins from the ``distlift.plugins`` entry point group."""
        candidates = discover_entry_point_plugins()
        return load_plugins(candidates)

    def load_explicit_plugins(
        self, paths: Sequence[Path]
    ) -> list[DistliftPlugin]:
        """Load plugins from explicit filesystem paths.

        Args:
            paths: ``.py`` files or package directories.
        """
        candidates = discover_plugins_from_paths(paths)
        return load_plugins(candidates)
