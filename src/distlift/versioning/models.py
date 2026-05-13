"""Frozen attrs models representing versions and release selections."""

from __future__ import annotations

import attrs

from distlift.config.models import BumpKind, VersionFormat


@attrs.define(frozen=True)
class VersionParts:
    """Decomposed version components aligned with a configured format.

    Attributes:
        major: Major version component (non-negative integer).
        minor: Minor component for major.minor and three-part formats.
        patch: Patch component for three-part semver-like formats.
        fmt: Version format governing how this value is parsed and rendered.
    """

    major: int
    minor: int = 0
    patch: int = 0
    fmt: VersionFormat = VersionFormat.MAJOR_MINOR_PATCH

    def __str__(self) -> str:
        """Return this version formatted according to ``fmt``."""

        # Import locally to avoid a circular import with the formatter module
        from distlift.versioning.formatter import format_version

        return format_version(self)


@attrs.define(frozen=True)
class VersionSelection:
    """How the next version should be chosen for a release run.

    Attributes:
        bump: Requested bump when not supplying an explicit version string.
        explicit: Raw explicit version text when bypassing bump resolution.
    """

    bump: BumpKind | None = None
    explicit: str | None = None

    def is_explicit(self) -> bool:
        """Return whether an explicit version string was provided."""
        return self.explicit is not None


@attrs.define(frozen=True)
class ResolvedVersion:
    """Current and next versions plus the tag name to create.

    Attributes:
        current: Version inferred before applying bump or explicit selection.
        next: Target version after applying bump or explicit selection.
        tag_name: Fully expanded Git tag derived from the template and version.
        bump: Bump kind used to reach ``next``, or None when explicit was used.
        was_explicit: True when ``next`` came from an explicit version string.
    """

    current: VersionParts
    next: VersionParts
    tag_name: str
    bump: BumpKind | None
    was_explicit: bool
