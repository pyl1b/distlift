from __future__ import annotations

from distlift.config.models import VersionFormat
from distlift.errors import VersionError
from distlift.versioning.parser import parse_tag_version


def build_tag_pattern(template: str, package_name: str | None) -> str:
    """Return a glob pattern suitable for `git tag --list`."""
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
    """Return tags sorted ascending by their parsed version."""

    def _key(tag: str) -> tuple[int, int, int]:
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
    """Return the tag representing the highest version for the given package."""
    matching = []
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
