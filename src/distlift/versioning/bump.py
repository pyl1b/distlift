from __future__ import annotations

import attrs

from distlift.config.models import BumpKind, VersionFormat
from distlift.errors import VersionError
from distlift.versioning.models import VersionParts


def validate_bump_allowed(fmt: VersionFormat, bump: BumpKind) -> None:
    """Raise VersionError if the bump kind is not valid for the given format."""
    if fmt == VersionFormat.MAJOR and bump != BumpKind.MAJOR:
        raise VersionError(
            f"Bump '{bump.value}' is not allowed for version format '{fmt.value}'; "
            "only 'major' is valid"
        )
    if fmt == VersionFormat.MAJOR_MINOR and bump == BumpKind.PATCH:
        raise VersionError(
            f"Bump 'patch' is not allowed for version format '{fmt.value}'; "
            "use 'major' or 'minor'"
        )


def bump_version(parts: VersionParts, bump: BumpKind) -> VersionParts:
    """Return new VersionParts with the given component incremented."""
    validate_bump_allowed(parts.fmt, bump)

    if bump == BumpKind.MAJOR:
        return attrs.evolve(parts, major=parts.major + 1, minor=0, patch=0)
    if bump == BumpKind.MINOR:
        return attrs.evolve(parts, minor=parts.minor + 1, patch=0)
    return attrs.evolve(parts, patch=parts.patch + 1)


def coerce_initial_version(text: str, fmt: VersionFormat) -> VersionParts:
    """Parse a version string, falling back to 0.0.0 components if needed."""
    from distlift.versioning.parser import parse_version

    try:
        return parse_version(text, fmt)
    except VersionError:
        if fmt == VersionFormat.MAJOR:
            return VersionParts(major=0, fmt=fmt)
        if fmt == VersionFormat.MAJOR_MINOR:
            return VersionParts(major=0, minor=1, fmt=fmt)
        return VersionParts(major=0, minor=1, patch=0, fmt=fmt)
