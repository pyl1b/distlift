"""Manifest handler interface and built-in handler registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class ManifestHandler(ABC):
    """Strategy for reading and writing one manifest format.

    Subclasses implement format-specific detection, version I/O, and
    dynamic-version checks.  Handlers are registered by ``kind`` string so
    third-party plugins can add new manifest formats without changing the
    ``Language`` enum.
    """

    @abstractmethod
    def detect(self, root: Path) -> Path | None:
        """Return the default manifest path under ``root``, or ``None``.

        Args:
            root: Directory to search for the manifest file.
        """

    @abstractmethod
    def read_version(self, path: Path) -> str | None:
        """Return the version string declared in ``path``, or ``None``.

        Args:
            path: Absolute path to the manifest file.
        """

    @abstractmethod
    def write_version(self, path: Path, version: str) -> None:
        """Persist ``version`` into the manifest at ``path``.

        Args:
            path: Absolute path to the manifest file.
            version: New version string to write.
        """

    @abstractmethod
    def is_dynamic(self, path: Path) -> bool:
        """Return True when the version in ``path`` is computed, not static.

        Args:
            path: Absolute path to the manifest file.
        """


class PyprojectHandler(ManifestHandler):
    """Manifest handler for ``pyproject.toml`` files."""

    def detect(self, root: Path) -> Path | None:
        candidate = root / "pyproject.toml"
        return candidate if candidate.is_file() else None

    def read_version(self, path: Path) -> str | None:
        from distlift.manifests.pyproject_file import (
            get_project_version,
            read_pyproject,
        )

        data = read_pyproject(path)
        return get_project_version(data)

    def write_version(self, path: Path, version: str) -> None:
        from distlift.manifests.pyproject_file import set_project_version

        set_project_version(path, version)

    def is_dynamic(self, path: Path) -> bool:
        from distlift.manifests.pyproject_file import (
            project_uses_dynamic_version,
            read_pyproject,
        )

        try:
            data = read_pyproject(path)
            return project_uses_dynamic_version(data)
        except Exception:
            return False


class PackageJsonHandler(ManifestHandler):
    """Manifest handler for ``package.json`` files."""

    def detect(self, root: Path) -> Path | None:
        candidate = root / "package.json"
        return candidate if candidate.is_file() else None

    def read_version(self, path: Path) -> str | None:
        from distlift.manifests.package_json_file import (
            get_package_version,
            read_package_json,
        )

        data = read_package_json(path)
        return get_package_version(data)

    def write_version(self, path: Path, version: str) -> None:
        from distlift.manifests.package_json_file import set_package_version

        set_package_version(path, version)

    def is_dynamic(self, path: Path) -> bool:
        return False


class SynologyInfoHandler(ManifestHandler):
    """Manifest handler for Synology DSM ``INFO`` package metadata files."""

    def detect(self, root: Path) -> Path | None:
        candidate = root / "packaging" / "synology" / "INFO"
        return candidate if candidate.is_file() else None

    def read_version(self, path: Path) -> str | None:
        from distlift.manifests.synology_info_file import read_info_version

        return read_info_version(path)

    def write_version(self, path: Path, version: str) -> None:
        from distlift.manifests.synology_info_file import set_info_version

        set_info_version(path, version)

    def is_dynamic(self, path: Path) -> bool:
        return False


class PythonVersionHandler(ManifestHandler):
    """Manifest handler for Python ``__version__.py`` files."""

    def detect(self, root: Path) -> Path | None:
        """Return no implicit file for root-level auto-detection.

        Args:
            root: Directory that may contain a project.
        """
        return None

    def read_version(self, path: Path) -> str | None:
        """Read ``__version__`` from ``path``.

        Args:
            path: Python version file to inspect.
        """
        from distlift.manifests.python_version_file import (
            read_python_version,
        )

        return read_python_version(path)

    def write_version(self, path: Path, version: str) -> None:
        """Write ``version`` into ``path``.

        Args:
            path: Python version file to update.
            version: New version string.
        """
        from distlift.manifests.python_version_file import (
            set_python_version,
        )

        set_python_version(path, version)

    def is_dynamic(self, path: Path) -> bool:
        """Return False because the file stores a static assignment.

        Args:
            path: Python version file to inspect.
        """
        return False


_BUILTIN_HANDLERS: dict[str, ManifestHandler] = {
    "pyproject": PyprojectHandler(),
    "package-json": PackageJsonHandler(),
    "synology-info": SynologyInfoHandler(),
    "python-version": PythonVersionHandler(),
}

_LANGUAGE_TO_KIND: dict[str, str] = {
    "python": "pyproject",
    "javascript": "package-json",
}


def get_handler(kind: str) -> ManifestHandler | None:
    """Return the registered handler for ``kind``, or ``None``.

    Args:
        kind: Manifest kind string such as ``"pyproject"`` or
            ``"package-json"``.
    """
    return _BUILTIN_HANDLERS.get(kind)


def register_handler(kind: str, handler: ManifestHandler) -> None:
    """Register a custom handler for ``kind``, replacing any existing entry.

    Args:
        kind: Manifest kind string.
        handler: Handler instance to register.
    """
    _BUILTIN_HANDLERS[kind] = handler


def kind_for_language(language: str) -> str | None:
    """Return the default manifest kind for a language name, or ``None``.

    Args:
        language: Language enum value string (e.g. ``"python"``).
    """
    return _LANGUAGE_TO_KIND.get(language)
