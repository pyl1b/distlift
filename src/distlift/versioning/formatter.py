"""String formatting for versions and Git tag names."""

from __future__ import annotations

from typing import TYPE_CHECKING

from distlift.config.models import VersionFormat

if TYPE_CHECKING:
    from distlift.versioning.models import VersionParts


def format_version(parts: VersionParts) -> str:
    """Format ``parts`` as a version string for its configured format.

    Args:
        parts: Structured version with an embedded ``VersionFormat``.
    """
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
    """Fill ``version`` and optional ``package_name`` into ``template``.

    Args:
        version: Already-formatted version text to embed in the tag.
        template: Tag template containing ``{version}`` and optional
            ``{package}`` placeholders.
        package_name: Monorepo package segment for ``{package}``, if present.
    """
    result = template.replace("{version}", version)

    if package_name is not None:
        result = result.replace("{package}", package_name)

    return result
