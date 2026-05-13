from __future__ import annotations

import attrs

from distlift.errors import PluginError, UnsupportedLanguageError
from distlift.plugins.base import (
    GitBackendPlugin,
    LanguagePlugin,
    ManifestPlugin,
    PublishPlugin,
    VersionSourcePlugin,
)


@attrs.define
class RegisteredPlugin:
    plugin: object
    source: str
    overrides: str | None = None


@attrs.define
class PluginRegistry:
    _language_plugins: dict[str, RegisteredPlugin] = attrs.Factory(dict)
    _manifest_plugins: dict[str, RegisteredPlugin] = attrs.Factory(dict)
    _publish_plugins: dict[str, RegisteredPlugin] = attrs.Factory(dict)
    _version_source_plugins: dict[str, RegisteredPlugin] = attrs.Factory(dict)
    _git_backend: RegisteredPlugin | None = None
    allow_override: bool = True

    def register_language_plugin(
        self, plugin: LanguagePlugin, source: str = "<unknown>"
    ) -> None:
        lang = plugin.get_language()
        if lang in self._language_plugins and not self.allow_override:
            raise PluginError(
                f"Language plugin '{lang}' already registered and overrides are disabled"
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
        kind = plugin.get_kind()
        if kind in self._manifest_plugins and not self.allow_override:
            raise PluginError(
                f"Manifest plugin '{kind}' already registered and overrides are disabled"
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
        lang = plugin.get_language()
        if lang in self._publish_plugins and not self.allow_override:
            raise PluginError(
                f"Publish plugin '{lang}' already registered and overrides are disabled"
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
        name = plugin.get_source_name()
        if name in self._version_source_plugins and not self.allow_override:
            raise PluginError(
                f"Version source plugin '{name}' already registered and overrides are disabled"
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
        if self._git_backend is not None and not self.allow_override:
            raise PluginError(
                "Git backend plugin already registered and overrides are disabled"
            )
        self._git_backend = RegisteredPlugin(
            plugin=plugin,
            source=source,
            overrides=self._git_backend.source if self._git_backend else None,
        )

    def get_language_plugin(self, language: str) -> LanguagePlugin:
        entry = self._language_plugins.get(language)
        if entry is None:
            raise UnsupportedLanguageError(
                f"No language plugin registered for '{language}'"
            )
        return entry.plugin  # type: ignore[return-value]

    def get_manifest_plugin(self, kind: str) -> ManifestPlugin:
        entry = self._manifest_plugins.get(kind)
        if entry is None:
            raise PluginError(
                f"No manifest plugin registered for kind '{kind}'"
            )
        return entry.plugin  # type: ignore[return-value]

    def get_publish_plugin(self, language: str) -> PublishPlugin | None:
        entry = self._publish_plugins.get(language)
        return entry.plugin if entry else None  # type: ignore[return-value]

    def get_git_backend(self) -> GitBackendPlugin:
        if self._git_backend is None:
            raise PluginError("No Git backend plugin registered")
        return self._git_backend.plugin  # type: ignore[return-value]

    def list_all(self) -> list[RegisteredPlugin]:
        result: list[RegisteredPlugin] = []
        result.extend(self._language_plugins.values())
        result.extend(self._manifest_plugins.values())
        result.extend(self._publish_plugins.values())
        result.extend(self._version_source_plugins.values())
        if self._git_backend:
            result.append(self._git_backend)
        return result

    def has_language(self, language: str) -> bool:
        return language in self._language_plugins
