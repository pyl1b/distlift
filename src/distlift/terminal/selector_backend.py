"""Selector backends for interactive dependency upgrades."""

from __future__ import annotations

from typing import Protocol

from distlift.dependencies.upgrade_models import (
    DependencySelection,
    DependencyVersionChoice,
    PackageSource,
)


class SelectorCancelledError(Exception):
    """Raised when the user cancels dependency selection.

    Attributes:
        None beyond the attributes inherited from ``Exception``.
    """


class SelectorBackend(Protocol):
    """Protocol for dependency selection UIs."""

    def select(
        self,
        source: PackageSource,
        choices: list[DependencyVersionChoice],
    ) -> list[DependencySelection]:
        """Return user selections for one package source.

        Args:
            source: Package source being reviewed.
            choices: Dependency rows with registry metadata.
        """


class ScriptedSelectorBackend:
    """Test backend that returns predetermined selections.

    Attributes:
        _responses: Mapping from project name to selection list.
    """

    def __init__(
        self,
        responses: dict[str, list[DependencySelection]] | None = None,
    ) -> None:
        self._responses = responses or {}

    def select(
        self,
        source: PackageSource,
        choices: list[DependencyVersionChoice],
    ) -> list[DependencySelection]:
        """Return scripted selections for the requested source.

        Args:
            source: Package source being reviewed.
            choices: Dependency rows with registry metadata.
        """
        if source.project.name in self._responses:
            return self._responses[source.project.name]

        return [
            DependencySelection(
                dependency=choice.dependency,
                target_version=None,
                cycle_index=0,
            )
            for choice in choices
        ]
