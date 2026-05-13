from __future__ import annotations

from typing import TYPE_CHECKING

from distlift.config.models import VersionFormat

if TYPE_CHECKING:
    from distlift.versioning.models import VersionParts


def format_version(parts: VersionParts) -> str:
    """Format a VersionParts into a version string matching its format."""
    if parts.fmt == VersionFormat.MAJOR:
        return str(parts.major)
    if parts.fmt == VersionFormat.MAJOR_MINOR:
        return f"{parts.major}.{parts.minor}"
    return f"{parts.major}.{parts.minor}.{parts.patch}"


def format_tag(
    version: str,
    template: str,
    package_name: str | None = None,
) -> str:
    """Build a tag string by substituting version (and optionally package) into the template."""
    result = template.replace("{version}", version)
    if package_name is not None:
        result = result.replace("{package}", package_name)
    return result
