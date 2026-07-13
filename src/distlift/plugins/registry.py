from __future__ import annotations

import attrs

from distlift.errors import PluginError, UnsupportedLanguageError
from distlift.plugins.base import (
    ChangelogPlugin,
    DependencyUpdaterPlugin,
    GitBackendPlugin,
    LanguagePlugin,
    ManifestPlugin,
    PackageManagerPlugin,
    PublishPlugin,
    VersionSourcePlugin,
)


@attrs.define
class RegisteredPlugin:
    """Metadata for one plugin entry stored in a PluginRegistry.

    Attributes:
        plugin: The concrete plugin instance.
        source: Human-readable origin (e.g. entry point name or path).
        overrides: When set, the prior ``source`` replaced by this entry.
    """

    plugin: object
    source: str
    overrides: str | None = None


def _empty_registered_map() -> dict[str, RegisteredPlugin]:
    """Return a new empty map for plugin registry buckets."""
    return {}


@attrs.define
class PluginRegistry:
    """Holds at most one active plugin per capability key.

    Attributes:
        allow_override: When True, later registrations replace earlier ones.

        _language_plugins: Map of language id to registered language plugin.
        _manifest_plugins: Map of manifest kind to registered manifest plugin.
        _publish_plugins: Map of language id to registered publish plugin.
        _version_source_plugins: Map of version source name to plugin.
        _git_backend: Optional registered Git backend plugin.
        _changelog_plugin: Optional registered changelog formatter plugin.
        _dependency_update_plugins: Map of updater name to registered plugin.
        _package_manager_plugins: Map of manager name to registered plugin.
    """

    allow_override: bool = True

    _language_plugins: dict[str, RegisteredPlugin] = attrs.Factory(
        _empty_registered_map
    )
    _manifest_plugins: dict[str, RegisteredPlugin] = attrs.Factory(
        _empty_registered_map
    )
    _publish_plugins: dict[str, RegisteredPlugin] = attrs.Factory(
        _empty_registered_map
    )
    _version_source_plugins: dict[str, RegisteredPlugin] = attrs.Factory(
        _empty_registered_map
    )
    _git_backend: RegisteredPlugin | None = None
    _changelog_plugin: RegisteredPlugin | None = None
    _dependency_update_plugins: dict[str, RegisteredPlugin] = attrs.Factory(
        _empty_registered_map
    )
    _package_manager_plugins: dict[str, RegisteredPlugin] = attrs.Factory(
        _empty_registered_map
    )

    def register_language_plugin(
        self, plugin: LanguagePlugin, source: str = "<unknown>"
    ) -> None:
        """Register or replace the plugin for ``plugin.get_language()``.

        Args:
            plugin: Language plugin instance to register.
            source: Provenance label for diagnostics.
        """
        lang = plugin.get_language()

        if lang in self._language_plugins and not self.allow_override:
            raise PluginError(
                f"Language plugin {lang!r} already registered; "
                "overrides are disabled"
            )

        prev = self._language_plugins.get(lang)
        self._language_plugins[lang] = RegisteredPlugin(
            plugin=plugin,
            source=source,
            overrides=prev.source if prev else None,
        )

    def register_manifest_plugin(
        self, plugin: ManifestPlugin, source: str = "<unknown>"
    ) -> None:
        """Register or replace the manifest plugin for ``plugin.get_kind()``.

        Args:
            plugin: Manifest plugin instance to register.
            source: Provenance label for diagnostics.
        """
        kind = plugin.get_kind()

        if kind in self._manifest_plugins and not self.allow_override:
            raise PluginError(
                f"Manifest plugin {kind!r} already registered; "
                "overrides are disabled"
            )

        prev = self._manifest_plugins.get(kind)
        self._manifest_plugins[kind] = RegisteredPlugin(
            plugin=plugin,
            source=source,
            overrides=prev.source if prev else None,
        )

    def register_publish_plugin(
        self, plugin: PublishPlugin, source: str = "<unknown>"
    ) -> None:
        """Register or replace the publish plugin for the active language.

        The capability key is ``plugin.get_language()``.

        Args:
            plugin: Publish plugin instance to register.
            source: Provenance label for diagnostics.
        """
        lang = plugin.get_language()

        if lang in self._publish_plugins and not self.allow_override:
            raise PluginError(
                f"Publish plugin {lang!r} already registered; "
                "overrides are disabled"
            )

        prev = self._publish_plugins.get(lang)
        self._publish_plugins[lang] = RegisteredPlugin(
            plugin=plugin,
            source=source,
            overrides=prev.source if prev else None,
        )

    def register_version_source_plugin(
        self, plugin: VersionSourcePlugin, source: str = "<unknown>"
    ) -> None:
        """Register or replace the plugin for ``plugin.get_source_name()``.

        Args:
            plugin: Version source plugin instance to register.
            source: Provenance label for diagnostics.
        """
        name = plugin.get_source_name()

        if name in self._version_source_plugins and not self.allow_override:
            raise PluginError(
                f"Version source plugin {name!r} already registered; "
                "overrides are disabled"
            )

        prev = self._version_source_plugins.get(name)
        self._version_source_plugins[name] = RegisteredPlugin(
            plugin=plugin,
            source=source,
            overrides=prev.source if prev else None,
        )

    def register_git_backend_plugin(
        self, plugin: GitBackendPlugin, source: str = "<unknown>"
    ) -> None:
        """Register or replace the single Git backend plugin.

        Args:
            plugin: Git backend plugin instance to register.
            source: Provenance label for diagnostics.
        """
        if self._git_backend is not None and not self.allow_override:
            raise PluginError(
                "Git backend plugin already registered; overrides are disabled"
            )

        self._git_backend = RegisteredPlugin(
            plugin=plugin,
            source=source,
            overrides=self._git_backend.source if self._git_backend else None,
        )

    def register_dependency_updater_plugin(
        self, plugin: DependencyUpdaterPlugin, source: str = "<unknown>"
    ) -> None:
        """Register or replace the plugin for ``plugin.get_updater_name()``.

        Args:
            plugin: Dependency updater plugin instance to register.
            source: Provenance label for diagnostics.
        """
        name = plugin.get_updater_name()

        if name in self._dependency_update_plugins and not self.allow_override:
            raise PluginError(
                f"Dependency updater plugin {name!r} already registered; "
                "overrides are disabled"
            )

        prev = self._dependency_update_plugins.get(name)
        self._dependency_update_plugins[name] = RegisteredPlugin(
            plugin=plugin,
            source=source,
            overrides=prev.source if prev else None,
        )

    def register_changelog_plugin(
        self, plugin: ChangelogPlugin, source: str = "<unknown>"
    ) -> None:
        """Register or replace the changelog formatter plugin.

        Args:
            plugin: Changelog plugin instance to register.
            source: Provenance label for diagnostics.
        """
        if self._changelog_plugin is not None and not self.allow_override:
            raise PluginError(
                "Changelog plugin already registered; overrides are disabled"
            )

        self._changelog_plugin = RegisteredPlugin(
            plugin=plugin,
            source=source,
            overrides=(
                self._changelog_plugin.source
                if self._changelog_plugin
                else None
            ),
        )

    def register_package_manager_plugin(
        self, plugin: PackageManagerPlugin, source: str = "<unknown>"
    ) -> None:
        """Register or replace the plugin for ``plugin.get_manager_name()``.

        Args:
            plugin: Package manager plugin instance to register.
            source: Provenance label for diagnostics.
        """
        name = plugin.get_manager_name()

        if name in self._package_manager_plugins and not self.allow_override:
            raise PluginError(
                f"Package manager plugin {name!r} already registered; "
                "overrides are disabled"
            )

        prev = self._package_manager_plugins.get(name)
        self._package_manager_plugins[name] = RegisteredPlugin(
            plugin=plugin,
            source=source,
            overrides=prev.source if prev else None,
        )

    def get_language_plugin(self, language: str) -> LanguagePlugin:
        """Return the registered language plugin for ``language``.

        Args:
            language: Language identifier string (e.g. ``python``).

        Raises:
            UnsupportedLanguageError: When no plugin exists for ``language``.
        """
        entry = self._language_plugins.get(language)
        if entry is None:
            raise UnsupportedLanguageError(
                f"No language plugin registered for '{language}'"
            )
        return entry.plugin  # type: ignore[return-value]

    def get_manifest_plugin(self, kind: str) -> ManifestPlugin:
        """Return the registered manifest plugin for ``kind``.

        Args:
            kind: Manifest kind string (e.g. ``pyproject``).

        Raises:
            PluginError: When no plugin is registered for ``kind``.
        """
        entry = self._manifest_plugins.get(kind)
        if entry is None:
            raise PluginError(
                f"No manifest plugin registered for kind '{kind}'"
            )
        return entry.plugin  # type: ignore[return-value]

    def get_publish_plugin(self, language: str) -> PublishPlugin | None:
        """Return the publish plugin for ``language``, if any.

        Args:
            language: Language identifier string.
        """
        entry = self._publish_plugins.get(language)
        return entry.plugin if entry else None  # type: ignore[return-value]

    def get_git_backend(self) -> GitBackendPlugin:
        """Return the registered Git backend plugin.

        Raises:
            PluginError: When no Git backend has been registered.
        """
        if self._git_backend is None:
            raise PluginError("No Git backend plugin registered")
        return self._git_backend.plugin  # type: ignore[return-value]

    def get_dependency_updater_plugins(self) -> list[DependencyUpdaterPlugin]:
        """Return all registered dependency updater plugins.

        Returns:
            List of dependency updater plugin instances.
        """
        return [
            entry.plugin  # type: ignore[misc]
            for entry in self._dependency_update_plugins.values()
        ]

    def get_package_manager_plugins(self) -> list[PackageManagerPlugin]:
        """Return all registered package manager plugins.

        Returns:
            List of package manager plugin instances.
        """
        return [
            entry.plugin  # type: ignore[misc]
            for entry in self._package_manager_plugins.values()
        ]

    def get_package_manager_plugin(
        self, manager_name: str
    ) -> PackageManagerPlugin:
        """Return the registered package manager plugin by id.

        Args:
            manager_name: Package manager id such as ``pip`` or ``npm``.

        Raises:
            PluginError: When no plugin is registered for ``manager_name``.
        """
        entry = self._package_manager_plugins.get(manager_name)

        if entry is None:
            raise PluginError(
                f"No package manager plugin registered for {manager_name!r}"
            )

        return entry.plugin  # type: ignore[return-value]

    def get_changelog_plugin(self) -> ChangelogPlugin | None:
        """Return the registered changelog plugin when present.

        Returns:
            Registered changelog plugin or ``None`` when unset.
        """
        if self._changelog_plugin is None:
            return None

        return self._changelog_plugin.plugin  # type: ignore[return-value]

    def list_all(self) -> list[RegisteredPlugin]:
        """Return every ``RegisteredPlugin`` held in this registry."""
        result: list[RegisteredPlugin] = []
        result.extend(self._language_plugins.values())
        result.extend(self._manifest_plugins.values())
        result.extend(self._publish_plugins.values())
        result.extend(self._version_source_plugins.values())
        result.extend(self._dependency_update_plugins.values())
        result.extend(self._package_manager_plugins.values())
        if self._git_backend:
            result.append(self._git_backend)
        if self._changelog_plugin:
            result.append(self._changelog_plugin)
        return result

    def has_language(self, language: str) -> bool:
        """Return True when a language plugin is registered for ``language``.

        Args:
            language: Language identifier string.
        """
        return language in self._language_plugins
