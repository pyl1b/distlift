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
    def test_finds_highest(self):
        tags = ["v1.0.0", "v1.2.0", "v0.9.0"]
        result = find_latest_matching_tag(
            tags, "v{version}", VersionFormat.MAJOR_MINOR_PATCH
        )
        assert result == "v1.2.0"

    def test_returns_none_when_no_match(self):
        result = find_latest_matching_tag(
            [], "v{version}", VersionFormat.MAJOR_MINOR_PATCH
        )
        assert result is None

    def test_ignores_non_matching(self):
        tags = ["v1.0.0", "release-2.0"]
        result = find_latest_matching_tag(
            tags, "v{version}", VersionFormat.MAJOR_MINOR_PATCH
        )
        assert result == "v1.0.0"


class TestResolveCurrentVersion:
    def test_uses_latest_tag(self):
        tags = ["v1.0.0", "v2.0.0"]
        p = resolve_current_version(
            tags, "v{version}", VersionFormat.MAJOR_MINOR_PATCH, "0.1.0"
        )
        assert p.major == 2

    def test_falls_back_to_default(self):
        p = resolve_current_version(
            [], "v{version}", VersionFormat.MAJOR_MINOR_PATCH, "1.2.3"
        )
        assert (p.major, p.minor, p.patch) == (1, 2, 3)


class TestResolveNextVersion:
    def test_bump(self):
        current = VersionParts(major=1, minor=2, patch=3)
        result = resolve_next_version(
            current, BumpKind.PATCH, None, VersionFormat.MAJOR_MINOR_PATCH, "v{version}"
        )
        assert (result.next.major, result.next.minor, result.next.patch) == (1, 2, 4)
        assert result.tag_name == "v1.2.4"

    def test_explicit(self):
        current = VersionParts(major=1, minor=0, patch=0)
        result = resolve_next_version(
            current, None, "2.0.0", VersionFormat.MAJOR_MINOR_PATCH, "v{version}"
        )
        assert result.next.major == 2
        assert result.was_explicit

    def test_both_raises(self):
        current = VersionParts(major=1, minor=0, patch=0)
        with pytest.raises(VersionError):
            resolve_next_version(
                current,
                BumpKind.MAJOR,
                "2.0.0",
                VersionFormat.MAJOR_MINOR_PATCH,
                "v{version}",
            )

    def test_neither_raises(self):
        current = VersionParts(major=1, minor=0, patch=0)
        with pytest.raises(VersionError):
            resolve_next_version(
                current, None, None, VersionFormat.MAJOR_MINOR_PATCH, "v{version}"
            )
