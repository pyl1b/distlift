import pytest

from distlift.config.models import BumpKind, VersionFormat
from distlift.errors import VersionError
from distlift.versioning.bump import bump_version, validate_bump_allowed
from distlift.versioning.models import VersionParts


class TestBumpVersion:
    def test_bump_major(self):
        p = VersionParts(major=1, minor=2, patch=3)
        result = bump_version(p, BumpKind.MAJOR)
        assert (result.major, result.minor, result.patch) == (2, 0, 0)

    def test_bump_minor(self):
        p = VersionParts(major=1, minor=2, patch=3)
        result = bump_version(p, BumpKind.MINOR)
        assert (result.major, result.minor, result.patch) == (1, 3, 0)

    def test_bump_patch(self):
        p = VersionParts(major=1, minor=2, patch=3)
        result = bump_version(p, BumpKind.PATCH)
        assert (result.major, result.minor, result.patch) == (1, 2, 4)


class TestValidateBumpAllowed:
    def test_major_format_allows_major(self):
        validate_bump_allowed(
            VersionFormat.MAJOR, BumpKind.MAJOR
        )  # no exception

    def test_major_format_rejects_minor(self):
        with pytest.raises(VersionError):
            validate_bump_allowed(VersionFormat.MAJOR, BumpKind.MINOR)

    def test_major_format_rejects_patch(self):
        with pytest.raises(VersionError):
            validate_bump_allowed(VersionFormat.MAJOR, BumpKind.PATCH)

    def test_major_minor_format_allows_major(self):
        validate_bump_allowed(VersionFormat.MAJOR_MINOR, BumpKind.MAJOR)

    def test_major_minor_format_allows_minor(self):
        validate_bump_allowed(VersionFormat.MAJOR_MINOR, BumpKind.MINOR)

    def test_major_minor_format_rejects_patch(self):
        with pytest.raises(VersionError):
            validate_bump_allowed(VersionFormat.MAJOR_MINOR, BumpKind.PATCH)

    def test_full_format_allows_all(self):
        for kind in BumpKind:
            validate_bump_allowed(VersionFormat.MAJOR_MINOR_PATCH, kind)
