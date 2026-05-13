"""Tests for version bumping and bump-format validation."""

import pytest

from distlift.config.models import BumpKind, VersionFormat
from distlift.errors import VersionError
from distlift.versioning.bump import bump_version, validate_bump_allowed
from distlift.versioning.models import VersionParts


class TestBumpVersion:
    """Tests for incrementing version components."""

    def test_bump_major(self) -> None:
        """Increment the major component and reset lower components."""

        # Build a full version with non-zero lower components.
        p = VersionParts(major=1, minor=2, patch=3)

        # Apply a major bump to the version.
        result = bump_version(p, BumpKind.MAJOR)

        # Confirm lower components are reset.
        assert (result.major, result.minor, result.patch) == (2, 0, 0)

    def test_bump_minor(self) -> None:
        """Increment the minor component and reset patch."""

        # Build a full version with a non-zero patch component.
        p = VersionParts(major=1, minor=2, patch=3)

        # Apply a minor bump to the version.
        result = bump_version(p, BumpKind.MINOR)

        # Confirm the patch component is reset.
        assert (result.major, result.minor, result.patch) == (1, 3, 0)

    def test_bump_patch(self) -> None:
        """Increment only the patch component."""

        # Build a full version with all components present.
        p = VersionParts(major=1, minor=2, patch=3)

        # Apply a patch bump to the version.
        result = bump_version(p, BumpKind.PATCH)

        # Confirm only the patch component changes.
        assert (result.major, result.minor, result.patch) == (1, 2, 4)


class TestValidateBumpAllowed:
    """Tests for valid bump kinds per version format."""

    def test_major_format_allows_major(self) -> None:
        """Allow major bumps for major-only versions."""

        # Validate the only supported bump for major-only versions.
        validate_bump_allowed(VersionFormat.MAJOR, BumpKind.MAJOR)

    def test_major_format_rejects_minor(self) -> None:
        """Reject minor bumps for major-only versions."""

        # Validate an unsupported minor bump for major-only versions.
        with pytest.raises(VersionError):
            validate_bump_allowed(VersionFormat.MAJOR, BumpKind.MINOR)

    def test_major_format_rejects_patch(self) -> None:
        """Reject patch bumps for major-only versions."""

        # Validate an unsupported patch bump for major-only versions.
        with pytest.raises(VersionError):
            validate_bump_allowed(VersionFormat.MAJOR, BumpKind.PATCH)

    def test_major_minor_format_allows_major(self) -> None:
        """Allow major bumps for major-minor versions."""

        # Validate a major bump for major-minor versions.
        validate_bump_allowed(VersionFormat.MAJOR_MINOR, BumpKind.MAJOR)

    def test_major_minor_format_allows_minor(self) -> None:
        """Allow minor bumps for major-minor versions."""

        # Validate a minor bump for major-minor versions.
        validate_bump_allowed(VersionFormat.MAJOR_MINOR, BumpKind.MINOR)

    def test_major_minor_format_rejects_patch(self) -> None:
        """Reject patch bumps for major-minor versions."""

        # Validate an unsupported patch bump for major-minor versions.
        with pytest.raises(VersionError):
            validate_bump_allowed(VersionFormat.MAJOR_MINOR, BumpKind.PATCH)

    def test_full_format_allows_all(self) -> None:
        """Allow every bump kind for full versions."""

        # Validate every bump kind against full semantic versions.
        for kind in BumpKind:
            validate_bump_allowed(VersionFormat.MAJOR_MINOR_PATCH, kind)
