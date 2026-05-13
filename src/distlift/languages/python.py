"""Python ``pyproject.toml`` project adapter and built-in language plugin."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from distlift.config.models import Language, ResolvedConfig, VersionSource
from distlift.errors import ManifestUpdateError
from distlift.languages.base import ProjectAdapter
from distlift.manifests.pyproject_file import (
    get_project_version,
    project_uses_dynamic_version,
    read_pyproject,
    set_project_version,
)
from distlift.plugins.base import LanguagePlugin
from distlift.plugins.registry import PluginRegistry

if TYPE_CHECKING:
    from distlift.release.models import ReleaseTarget


class PythonProjectAdapter(ProjectAdapter):
    """``ProjectAdapter`` for Python projects using ``pyproject.toml``.

    Attributes:
        (none; delegates to :mod:`distlift.manifests.pyproject_file`.)
    """

    def detect_project(self, root: Path) -> bool:
        """Return True when ``root`` contains ``pyproject.toml``.

        Args:
            root: Directory to inspect.
        """
        return (root / "pyproject.toml").exists()

    def load_release_target(
        self, root: Path, config: ResolvedConfig
    ) -> ReleaseTarget:
        """Build a Python ``ReleaseTarget`` rooted at ``root``.

        Args:
            root: Python project root.
            config: Resolved distlift configuration.
        """
        from distlift.release.models import (
            ReleaseTarget,  # avoid circular at runtime
        )

        manifest = config.manifest_path or (root / "pyproject.toml")
        return ReleaseTarget(
            language=Language.PYTHON,
            root=root,
            manifest_path=manifest,
            version_source=config.version_source,
        )

    def is_dynamic_version(self, target: ReleaseTarget) -> bool:
        """Return True when tags or ``[project].dynamic`` supply the version.

        Args:
            target: Release target whose manifest may be inspected.
        """
        if target.version_source == VersionSource.TAG:
            return True

        try:
            data = read_pyproject(target.manifest_path)
            return project_uses_dynamic_version(data)
        except ManifestUpdateError:
            return False

    def read_manifest_version(self, target: ReleaseTarget) -> str | None:
        """Return ``project.version`` from the manifest, or None on failure.

        Args:
            target: Release target pointing at the manifest path.
        """
        try:
            data = read_pyproject(target.manifest_path)
            return get_project_version(data)
        except ManifestUpdateError:
            return None

    def update_manifest_version(
        self, target: ReleaseTarget, version: str
    ) -> None:
        """Write ``version`` into the project's ``pyproject.toml``.

        Args:
            target: Release target pointing at the manifest path.
            version: New version string.
        """
        set_project_version(target.manifest_path, version)


class PythonProjectPlugin(LanguagePlugin):
    """Registers :class:`PythonProjectAdapter` as the ``python`` language.

    Attributes:
        (none; the adapter is constructed implicitly by callers.)
    """

    def get_name(self) -> str:
        """Return the built-in plugin name."""
        return "builtin-python"

    def get_version(self) -> str:
        """Return the bundled plugin version string."""
        return "1.0.0"

    def get_language(self) -> str:
        """Return :attr:`Language.PYTHON` as its config string value."""
        return Language.PYTHON.value

    def register(self, registry: PluginRegistry) -> None:
        """Register this plugin as the handler for Python projects.

        Args:
            registry: Registry receiving the language binding.
        """
        registry.register_language_plugin(self, source="builtin")
