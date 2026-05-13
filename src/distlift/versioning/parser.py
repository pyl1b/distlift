from __future__ import annotations

import re

from distlift.config.models import VersionFormat
from distlift.errors import VersionError
from distlift.versioning.models import VersionParts


def parse_version(text: str, fmt: VersionFormat) -> VersionParts:
    """Parse a version string according to the given format."""
    text = text.strip()
    if fmt == VersionFormat.MAJOR:
        m = re.fullmatch(r"(\d+)", text)
        if not m:
            raise VersionError(
                f"Version '{text}' is not valid for format '{fmt.value}' (expected N)"
            )
        return VersionParts(major=int(m.group(1)), minor=0, patch=0, fmt=fmt)

    if fmt == VersionFormat.MAJOR_MINOR:
        m = re.fullmatch(r"(\d+)\.(\d+)", text)
        if not m:
            raise VersionError(
                f"Version '{text}' is not valid for format '{fmt.value}' (expected N.N)"
            )
        return VersionParts(
            major=int(m.group(1)), minor=int(m.group(2)), patch=0, fmt=fmt
        )

    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", text)
    if not m:
        raise VersionError(
            f"Version '{text}' is not valid for format '{fmt.value}' (expected N.N.N)"
        )
    return VersionParts(
        major=int(m.group(1)),
        minor=int(m.group(2)),
        patch=int(m.group(3)),
        fmt=fmt,
    )


def strip_tag_prefix(tag: str) -> str:
    """Strip a leading 'v' or 'V' prefix from a tag."""
    if tag.startswith(("v", "V")):
        return tag[1:]
    return tag


def parse_tag_version(
    tag: str,
    template: str,
    fmt: VersionFormat,
    package_name: str | None = None,
) -> VersionParts:
    """Extract the version from a tag string using the given template."""
    version_text = _extract_version_from_tag(tag, template, package_name)
    return parse_version(version_text, fmt)


def _extract_version_from_tag(
    tag: str, template: str, package_name: str | None
) -> str:
    pattern = re.escape(template)
    pattern = pattern.replace(
        r"\{version\}", r"(?P<version>[^\-]+(?:\.[^\-]+)*)"
    )
    if package_name:
        pattern = pattern.replace(r"\{package\}", re.escape(package_name))
    else:
        pattern = pattern.replace(r"\{package\}", r"[^/]+")

    m = re.fullmatch(pattern, tag)
    if not m:
        raise VersionError(f"Tag '{tag}' does not match template '{template}'")
    return m.group("version")
