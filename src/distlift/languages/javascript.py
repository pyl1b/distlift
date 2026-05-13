"""JavaScript ``package.json`` project adapter and built-in language plugin."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from distlift.config.models import Language, ResolvedConfig, VersionSource
from distlift.errors import ManifestUpdateError
from distlift.languages.base import ProjectAdapter
from distlift.manifests.package_json_file import (
    get_package_version,
    read_package_json,
    set_package_version,
)
from distlift.plugins.base import LanguagePlugin
from distlift.plugins.registry import PluginRegistry

if TYPE_CHECKING:
    from distlift.release.models import ReleaseTarget


class JavaScriptProjectAdapter(ProjectAdapter):
    """``ProjectAdapter`` for JavaScript projects using ``package.json``.

    Attributes:
        (none; delegates to :mod:`distlift.manifests.package_json_file`.)
    """

    def detect_project(self, root: Path) -> bool:
        """Return True when ``root`` contains ``package.json``.

        Args:
            root: Directory to inspect.
        """
        return (root / "package.json").exists()

    def load_release_target(
        self, root: Path, config: ResolvedConfig
    ) -> ReleaseTarget:
        """Build a JavaScript ``ReleaseTarget`` rooted at ``root``.

        Args:
            root: JavaScript project root.
            config: Resolved distlift configuration.
        """
        from distlift.release.models import ReleaseTarget

        manifest = config.manifest_path or (root / "package.json")
        return ReleaseTarget(
            language=Language.JAVASCRIPT,
            root=root,
            manifest_path=manifest,
            version_source=config.version_source,
        )

    def is_dynamic_version(self, target: ReleaseTarget) -> bool:
        """Return True when versions are resolved from Git tags only.

        Args:
            target: Release target being inspected.
        """
        return target.version_source == VersionSource.TAG

    def read_manifest_version(self, target: ReleaseTarget) -> str | None:
        """Return ``version`` from ``package.json``, or None if that fails.

        Args:
            target: Release target pointing at the manifest path.
        """
        try:
            data = read_package_json(target.manifest_path)
            return get_package_version(data)
        except ManifestUpdateError:
            return None

    def update_manifest_version(
        self, target: ReleaseTarget, version: str
    ) -> None:
        """Write ``version`` into the project's ``package.json``.

        Args:
            target: Release target pointing at the manifest path.
            version: New version string.
        """
        set_package_version(target.manifest_path, version)


class JavaScriptProjectPlugin(LanguagePlugin):
    """Register ``JavaScriptProjectAdapter`` for the ``javascript`` language.

    Attributes:
        (none; the adapter is constructed implicitly by callers.)
    """

    def get_name(self) -> str:
        """Return the built-in plugin name."""
        return "builtin-javascript"

    def get_version(self) -> str:
        """Return the bundled plugin version string."""
        return "1.0.0"

    def get_language(self) -> str:
        """Return :attr:`Language.JAVASCRIPT` as its config string value."""
        return Language.JAVASCRIPT.value

    def register(self, registry: PluginRegistry) -> None:
        """Register this plugin as the handler for JavaScript projects.

        Args:
            registry: Registry receiving the language binding.
        """
        registry.register_language_plugin(self, source="builtin")
