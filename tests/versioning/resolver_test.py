"""Tests for resolving current and next release versions."""

import pytest

from distlift.config.models import BumpKind, VersionFormat
from distlift.errors import VersionError
from distlift.versioning.models import VersionParts
from distlift.versioning.resolver import (
    find_latest_matching_tag,
    resolve_current_version,
    resolve_next_version,
)


class TestFindLatestMatchingTag:
    """Tests for selecting the newest matching release tag."""

    def test_finds_highest(self) -> None:
        """Return the highest version among matching tags."""

        # Prepare several matching version tags.
        tags = ["v1.0.0", "v1.2.0", "v0.9.0"]

        # Resolve the latest tag that matches the simple tag template.
        result = find_latest_matching_tag(
            tags, "v{version}", VersionFormat.MAJOR_MINOR_PATCH
        )

        # Confirm semantic version ordering is used.
        assert result == "v1.2.0"

    def test_returns_none_when_no_match(self) -> None:
        """Return None when no tags are available."""

        # Resolve the latest tag from an empty tag list.
        result = find_latest_matching_tag(
            [], "v{version}", VersionFormat.MAJOR_MINOR_PATCH
        )

        # Confirm no fallback tag is fabricated.
        assert result is None

    def test_ignores_non_matching(self) -> None:
        """Ignore tags that do not match the configured template."""

        # Prepare one matching tag and one non-matching tag.
        tags = ["v1.0.0", "release-2.0"]

        # Resolve the latest tag for the configured template.
        result = find_latest_matching_tag(
            tags, "v{version}", VersionFormat.MAJOR_MINOR_PATCH
        )

        # Confirm only matching tags are considered.
        assert result == "v1.0.0"


class TestResolveCurrentVersion:
    """Tests for resolving the current project version."""

    def test_uses_latest_tag(self) -> None:
        """Use the latest matching tag as the current version."""

        # Prepare tags with increasing versions.
        tags = ["v1.0.0", "v2.0.0"]

        # Resolve the current version from repository tags.
        p = resolve_current_version(
            tags, "v{version}", VersionFormat.MAJOR_MINOR_PATCH, "0.1.0"
        )

        # Confirm the highest tag version is selected.
        assert p.major == 2

    def test_falls_back_to_default(self) -> None:
        """Use the configured default when no matching tag exists."""

        # Resolve the current version without any repository tags.
        p = resolve_current_version(
            [], "v{version}", VersionFormat.MAJOR_MINOR_PATCH, "1.2.3"
        )

        # Confirm the default version is parsed.
        assert (p.major, p.minor, p.patch) == (1, 2, 3)


class TestResolveNextVersion:
    """Tests for computing the next release version."""

    def test_bump(self) -> None:
        """Compute the next version from a bump kind."""

        # Start from a concrete current version.
        current = VersionParts(major=1, minor=2, patch=3)

        # Resolve the next version using a patch bump.
        result = resolve_next_version(
            current,
            BumpKind.PATCH,
            None,
            VersionFormat.MAJOR_MINOR_PATCH,
            "v{version}",
        )

        # Confirm the patch component and tag name are updated.
        assert (result.next.major, result.next.minor, result.next.patch) == (
            1,
            2,
            4,
        )
        assert result.tag_name == "v1.2.4"

    def test_explicit(self) -> None:
        """Use an explicitly supplied next version."""

        # Start from an existing current version.
        current = VersionParts(major=1, minor=0, patch=0)

        # Resolve the next version from an explicit version string.
        result = resolve_next_version(
            current,
            None,
            "2.0.0",
            VersionFormat.MAJOR_MINOR_PATCH,
            "v{version}",
        )

        # Confirm explicit versions are preserved in the selection metadata.
        assert result.next.major == 2
        assert result.was_explicit

    def test_both_raises(self) -> None:
        """Reject requests that provide both bump and explicit version."""

        # Start from an existing current version.
        current = VersionParts(major=1, minor=0, patch=0)

        # Resolve with mutually exclusive version selection inputs.
        with pytest.raises(VersionError):
            resolve_next_version(
                current,
                BumpKind.MAJOR,
                "2.0.0",
                VersionFormat.MAJOR_MINOR_PATCH,
                "v{version}",
            )

    def test_neither_raises(self) -> None:
        """Reject requests without bump or explicit version."""

        # Start from an existing current version.
        current = VersionParts(major=1, minor=0, patch=0)

        # Resolve without any next-version selection input.
        with pytest.raises(VersionError):
            resolve_next_version(
                current,
                None,
                None,
                VersionFormat.MAJOR_MINOR_PATCH,
                "v{version}",
            )
