from distlift.config.models import VersionFormat
from distlift.vcs.tags import (
    build_tag_pattern,
    find_latest_tag_for_package,
    sort_tags_by_version,
)


class TestBuildTagPattern:
    def test_simple(self):
        assert build_tag_pattern("v{version}", None) == "v*"

    def test_with_package(self):
        assert build_tag_pattern("v{version}-{package}", "lib") == "v*-lib"


class TestSortTagsByVersion:
    def test_ascending_order(self):
        tags = ["v1.2.0", "v0.9.0", "v1.10.0"]
        sorted_tags = sort_tags_by_version(
            tags, "v{version}", VersionFormat.MAJOR_MINOR_PATCH
        )
        assert sorted_tags[-1] == "v1.10.0"


class TestFindLatestTagForPackage:
    def test_finds_highest(self):
        tags = ["v1.0.0-corelib", "v2.0.0-corelib", "v1.5.0-otherlib"]
        result = find_latest_tag_for_package(
            tags, "v{version}-{package}", VersionFormat.MAJOR_MINOR_PATCH, "corelib"
        )
        assert result == "v2.0.0-corelib"

    def test_returns_none_if_no_match(self):
        assert (
            find_latest_tag_for_package(
                [], "v{version}", VersionFormat.MAJOR_MINOR_PATCH
            )
            is None
        )
