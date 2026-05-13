import pytest

from distlift.config.models import VersionFormat
from distlift.errors import VersionError
from distlift.versioning.parser import (
    parse_version,
    parse_tag_version,
    strip_tag_prefix,
)


class TestParseVersion:
    def test_major_format(self):
        p = parse_version("3", VersionFormat.MAJOR)
        assert p.major == 3
        assert p.minor == 0
        assert p.patch == 0

    def test_major_minor_format(self):
        p = parse_version("2.5", VersionFormat.MAJOR_MINOR)
        assert p.major == 2
        assert p.minor == 5

    def test_full_format(self):
        p = parse_version("1.2.3", VersionFormat.MAJOR_MINOR_PATCH)
        assert (p.major, p.minor, p.patch) == (1, 2, 3)

    def test_major_rejects_multi_part(self):
        with pytest.raises(VersionError):
            parse_version("1.2", VersionFormat.MAJOR)

    def test_patch_rejects_single_part(self):
        with pytest.raises(VersionError):
            parse_version("1", VersionFormat.MAJOR_MINOR_PATCH)

    def test_strips_whitespace(self):
        p = parse_version("  1.2.3  ", VersionFormat.MAJOR_MINOR_PATCH)
        assert p.major == 1


class TestParseTagVersion:
    def test_simple_template(self):
        p = parse_tag_version("v1.2.3", "v{version}", VersionFormat.MAJOR_MINOR_PATCH)
        assert (p.major, p.minor, p.patch) == (1, 2, 3)

    def test_monorepo_template(self):
        p = parse_tag_version(
            "v1.2.3-corelib",
            "v{version}-{package}",
            VersionFormat.MAJOR_MINOR_PATCH,
            package_name="corelib",
        )
        assert (p.major, p.minor, p.patch) == (1, 2, 3)

    def test_wrong_template_raises(self):
        with pytest.raises(VersionError):
            parse_tag_version("1.2.3", "v{version}", VersionFormat.MAJOR_MINOR_PATCH)


class TestStripTagPrefix:
    def test_strips_v(self):
        assert strip_tag_prefix("v1.2.3") == "1.2.3"

    def test_strips_capital_v(self):
        assert strip_tag_prefix("V2.0") == "2.0"

    def test_no_prefix(self):
        assert strip_tag_prefix("1.0.0") == "1.0.0"
