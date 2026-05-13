from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from distlift.config.models import ResolvedConfig
    from distlift.release.models import ReleaseTarget


class ProjectAdapter(ABC):
    """Interface for language-specific project detection and manifest management."""

    @abstractmethod
    def detect_project(self, root: Path) -> bool:
        """Return True if root looks like a project this adapter handles."""

    @abstractmethod
    def load_release_target(self, root: Path, config: ResolvedConfig) -> ReleaseTarget:
        """Build a ReleaseTarget for the project rooted at root."""

    @abstractmethod
    def is_dynamic_version(self, target: ReleaseTarget) -> bool:
        """Return True if the project derives its version from something other than the manifest."""

    @abstractmethod
    def read_manifest_version(self, target: ReleaseTarget) -> str | None:
        """Read the current version from the manifest file, or None if absent."""

    @abstractmethod
    def update_manifest_version(self, target: ReleaseTarget, version: str) -> None:
        """Write version into the manifest file."""
