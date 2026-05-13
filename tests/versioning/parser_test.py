"""Tests for parsing versions and extracting versions from tag names."""

import pytest

from distlift.config.models import VersionFormat
from distlift.errors import VersionError
from distlift.versioning.parser import (
    parse_tag_version,
    parse_version,
    strip_tag_prefix,
)


class TestParseVersion:
    """Tests for parsing plain version strings."""

    def test_major_format(self) -> None:
        """Parse a major-only version string."""

        # Parse a single-part version using the major-only format.
        p = parse_version("3", VersionFormat.MAJOR)

        # Confirm missing minor and patch fields default to zero.
        assert p.major == 3
        assert p.minor == 0
        assert p.patch == 0

    def test_major_minor_format(self) -> None:
        """Parse a major-minor version string."""

        # Parse a two-part version using the major-minor format.
        p = parse_version("2.5", VersionFormat.MAJOR_MINOR)

        # Confirm the major and minor components are populated.
        assert p.major == 2
        assert p.minor == 5

    def test_full_format(self) -> None:
        """Parse a full major-minor-patch version string."""

        # Parse a three-part semantic version.
        p = parse_version("1.2.3", VersionFormat.MAJOR_MINOR_PATCH)

        # Confirm every component is populated.
        assert (p.major, p.minor, p.patch) == (1, 2, 3)

    def test_major_rejects_multi_part(self) -> None:
        """Reject multi-part versions for major-only format."""

        # Parse an invalid major-only version.
        with pytest.raises(VersionError):
            parse_version("1.2", VersionFormat.MAJOR)

    def test_patch_rejects_single_part(self) -> None:
        """Reject single-part versions for full version format."""

        # Parse an incomplete full version.
        with pytest.raises(VersionError):
            parse_version("1", VersionFormat.MAJOR_MINOR_PATCH)

    def test_strips_whitespace(self) -> None:
        """Ignore surrounding whitespace around version strings."""

        # Parse a version with leading and trailing whitespace.
        p = parse_version("  1.2.3  ", VersionFormat.MAJOR_MINOR_PATCH)

        # Confirm the version was stripped before parsing.
        assert p.major == 1


class TestParseTagVersion:
    """Tests for parsing versions embedded in tag templates."""

    def test_simple_template(self) -> None:
        """Parse a version from a simple release tag."""

        # Parse a tag with only the version placeholder.
        p = parse_tag_version(
            "v1.2.3", "v{version}", VersionFormat.MAJOR_MINOR_PATCH
        )

        # Confirm the tag version components are extracted.
        assert (p.major, p.minor, p.patch) == (1, 2, 3)

    def test_monorepo_template(self) -> None:
        """Parse a version from a package-specific monorepo tag."""

        # Parse a tag that includes both version and package placeholders.
        p = parse_tag_version(
            "v1.2.3-corelib",
            "v{version}-{package}",
            VersionFormat.MAJOR_MINOR_PATCH,
            package_name="corelib",
        )

        # Confirm the package suffix is excluded from the parsed version.
        assert (p.major, p.minor, p.patch) == (1, 2, 3)

    def test_wrong_template_raises(self) -> None:
        """Reject tags that do not match the configured template."""

        # Parse a tag that does not include the required prefix.
        with pytest.raises(VersionError):
            parse_tag_version(
                "1.2.3", "v{version}", VersionFormat.MAJOR_MINOR_PATCH
            )


class TestStripTagPrefix:
    """Tests for removing conventional tag prefixes."""

    def test_strips_v(self) -> None:
        """Strip a lowercase v prefix."""

        # Strip the conventional lowercase prefix from a version tag.
        assert strip_tag_prefix("v1.2.3") == "1.2.3"

    def test_strips_capital_v(self) -> None:
        """Strip an uppercase V prefix."""

        # Strip the conventional uppercase prefix from a version tag.
        assert strip_tag_prefix("V2.0") == "2.0"

    def test_no_prefix(self) -> None:
        """Leave tags without a conventional prefix unchanged."""

        # Strip a tag that has no removable prefix.
        assert strip_tag_prefix("1.0.0") == "1.0.0"
