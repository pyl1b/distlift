"""Language-agnostic project adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from distlift.config.models import ResolvedConfig
    from distlift.release.models import ReleaseTarget


class ProjectAdapter(ABC):
    """Language-specific project detection and manifest version I/O.

    Attributes:
        (none; adapters are typically stateless strategy objects.)
    """

    @abstractmethod
    def detect_project(self, root: Path) -> bool:
        """Return True when ``root`` looks like a project this adapter handles.

        Args:
            root: Repository or package root directory.
        """

    @abstractmethod
    def load_release_target(
        self, root: Path, config: ResolvedConfig
    ) -> ReleaseTarget:
        """Build a ``ReleaseTarget`` for the project at ``root``.

        Args:
            root: Project root directory on disk.
            config: Fully merged distlift configuration.
        """

    @abstractmethod
    def is_dynamic_version(self, target: ReleaseTarget) -> bool:
        """Return True when the version is not a static manifest field.

        Args:
            target: Resolved release target for one package.
        """

    @abstractmethod
    def read_manifest_version(self, target: ReleaseTarget) -> str | None:
        """Read the declared version from the manifest, if any.

        Args:
            target: Resolved release target including ``manifest_path``.
        """

    @abstractmethod
    def update_manifest_version(
        self, target: ReleaseTarget, version: str
    ) -> None:
        """Persist ``version`` into the manifest file for ``target``.

        Args:
            target: Resolved release target including ``manifest_path``.
            version: New version string to write.
        """
