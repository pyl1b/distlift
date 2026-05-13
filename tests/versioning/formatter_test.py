"""Tests for rendering versions and tags."""

from distlift.config.models import VersionFormat
from distlift.versioning.formatter import format_tag, format_version
from distlift.versioning.models import VersionParts


class TestFormatVersion:
    """Tests for formatting version component models."""

    def test_major(self) -> None:
        """Format a major-only version."""

        # Format a version configured for major-only output.
        assert (
            format_version(VersionParts(major=3, fmt=VersionFormat.MAJOR))
            == "3"
        )

    def test_major_minor(self) -> None:
        """Format a major-minor version."""

        # Format a version configured for major-minor output.
        assert (
            format_version(
                VersionParts(major=1, minor=2, fmt=VersionFormat.MAJOR_MINOR)
            )
            == "1.2"
        )

    def test_full(self) -> None:
        """Format a full major-minor-patch version."""

        # Format a version using the default full output format.
        assert (
            format_version(VersionParts(major=1, minor=2, patch=3)) == "1.2.3"
        )


class TestFormatTag:
    """Tests for applying release tag templates."""

    def test_simple_template(self) -> None:
        """Format a tag from a template with only version."""

        # Apply the simple release tag template.
        assert format_tag("1.2.3", "v{version}") == "v1.2.3"

    def test_monorepo_template(self) -> None:
        """Format a tag from a package-aware monorepo template."""

        # Apply the monorepo tag template with a package name.
        assert (
            format_tag("1.2.3", "v{version}-{package}", "corelib")
            == "v1.2.3-corelib"
        )

    def test_template_without_package(self) -> None:
        """Format a version-only tag without a package name."""

        # Apply a version-only template while omitting the package argument.
        assert format_tag("2.0.0", "v{version}") == "v2.0.0"
