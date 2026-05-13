"""Resolve current and next versions from tags, bumps, and explicit strings."""

from __future__ import annotations

from distlift.config.models import BumpKind, VersionFormat
from distlift.errors import VersionError
from distlift.versioning.bump import bump_version, coerce_initial_version
from distlift.versioning.formatter import format_tag, format_version
from distlift.versioning.models import ResolvedVersion, VersionParts
from distlift.versioning.parser import parse_tag_version, parse_version


def find_latest_matching_tag(
    tags: list[str],
    template: str,
    fmt: VersionFormat,
    package_name: str | None = None,
) -> str | None:
    """Return the highest-version tag among those matching ``template``.

    Args:
        tags: All candidate tag names from Git, in any order.
        template: Tag template with ``{version}`` and optional ``{package}``.
        fmt: Version format used when comparing parsed versions.
        package_name: Package segment for monorepo templates, if applicable.
    """
    from distlift.vcs.tags import sort_tags_by_version

    matching: list[str] = []

    # Keep tags whose names conform to the template and parse as versions
    for tag in tags:
        try:
            parse_tag_version(tag, template, fmt, package_name)
        except VersionError:
            continue

        matching.append(tag)

    if not matching:
        return None

    sorted_tags = sort_tags_by_version(matching, template, fmt, package_name)

    return sorted_tags[-1] if sorted_tags else None


def resolve_current_version(
    tags: list[str],
    template: str,
    fmt: VersionFormat,
    default_version: str,
    package_name: str | None = None,
) -> VersionParts:
    """Infer the current version from tags or coerce ``default_version``.

    Args:
        tags: Tag names visible to the resolver, typically from Git.
        template: Tag template with ``{version}`` and optional ``{package}``.
        fmt: Configured version format for parsing and coercion.
        default_version: Fallback version text when no matching tag exists.
        package_name: Package segment for monorepo templates, if applicable.
    """
    latest = find_latest_matching_tag(tags, template, fmt, package_name)

    if latest is None:
        return coerce_initial_version(default_version, fmt)

    return parse_tag_version(latest, template, fmt, package_name)


def resolve_next_version(
    current: VersionParts,
    bump: BumpKind | None,
    explicit: str | None,
    fmt: VersionFormat,
    template: str,
    package_name: str | None = None,
) -> ResolvedVersion:
    """Compute the next version and tag name from bump or explicit input.

    Args:
        current: Established current version parts before the release.
        bump: Requested bump when not using an explicit next version.
        explicit: Raw explicit next version text, mutually exclusive with bump.
        fmt: Version format enforced when parsing ``explicit``.
        template: Tag template for the resolved ``tag_name``.
        package_name: Package segment for monorepo templates, if applicable.

    Raises:
        VersionError: When bump and explicit are both set or both missing.
    """
    if explicit is not None and bump is not None:
        raise VersionError(
            "Provide either an explicit version or a bump kind, not both"
        )

    if explicit is None and bump is None:
        raise VersionError("A bump kind or explicit version is required")

    if explicit is not None:
        next_parts = parse_version(explicit, fmt)
        tag_name = format_tag(
            format_version(next_parts),
            template,
            package_name,
        )

        return ResolvedVersion(
            current=current,
            next=next_parts,
            tag_name=tag_name,
            bump=None,
            was_explicit=True,
        )

    assert bump is not None
    next_parts = bump_version(current, bump)
    tag_name = format_tag(
        format_version(next_parts),
        template,
        package_name,
    )

    return ResolvedVersion(
        current=current,
        next=next_parts,
        tag_name=tag_name,
        bump=bump,
        was_explicit=False,
    )
