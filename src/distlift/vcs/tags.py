"""Tag glob patterns, version-ordered sorting, and latest-tag selection."""

from __future__ import annotations

from distlift.config.models import VersionFormat
from distlift.errors import VersionError
from distlift.versioning.parser import parse_tag_version


def build_tag_pattern(template: str, package_name: str | None) -> str:
    """Build a ``git tag --list`` glob from a distlift tag template.

    Args:
        template: Tag template containing ``{version}`` and optionally
            ``{package}`` placeholders.
        package_name: Concrete package segment, or None to keep a wildcard.

    Returns:
        A glob pattern where version and optional package slots are ``*``.
    """
    pattern = template.replace("{version}", "*")

    if package_name:
        pattern = pattern.replace("{package}", package_name)
    else:
        pattern = pattern.replace("{package}", "*")

    return pattern


def sort_tags_by_version(
    tags: list[str],
    template: str,
    fmt: VersionFormat,
    package_name: str | None = None,
) -> list[str]:
    """Sort ``tags`` ascending by parsed semantic components.

    Args:
        tags: Raw tag names produced by Git.
        template: Tag template used to extract embedded versions.
        fmt: Version format controlling parser strictness.
        package_name: Monorepo package segment, or None for simple repos.

    Returns:
        The same tag strings ordered from lowest to highest version; tags
        that fail parsing sort before all valid tags.
    """

    def _key(tag: str) -> tuple[int, int, int]:
        """Map ``tag`` to a tuple sort key, using sentinel values on failure.

        Args:
            tag: Candidate tag string from Git.
        """
        try:
            parts = parse_tag_version(tag, template, fmt, package_name)
            return (parts.major, parts.minor, parts.patch)
        except VersionError:
            return (-1, -1, -1)

    return sorted(tags, key=_key)


def find_latest_tag_for_package(
    tags: list[str],
    template: str,
    fmt: VersionFormat,
    package_name: str | None = None,
) -> str | None:
    """Return the tag with the highest successfully parsed version.

    Args:
        tags: Raw tag names produced by Git.
        template: Tag template used to extract embedded versions.
        fmt: Version format controlling parser strictness.
        package_name: Monorepo package segment, or None for simple repos.

    Returns:
        The newest valid tag, or None when no tag parses successfully.
    """
    matching = []

    # Keep only names that conform to the template and format rules
    for tag in tags:
        try:
            parse_tag_version(tag, template, fmt, package_name)
            matching.append(tag)
        except VersionError:
            continue

    if not matching:
        return None

    sorted_tags = sort_tags_by_version(matching, template, fmt, package_name)

    return sorted_tags[-1]
