"""Tests for ``next_deploy_tag_name``."""

from __future__ import annotations

from distlift.deploy.tags import next_deploy_tag_name


class TestNextDeployTagName:
    """Tests for sequential deploy marker tag names."""

    def test_starts_at_one_when_missing(self) -> None:
        """First tag for a prefix uses suffix ``_1``."""

        assert next_deploy_tag_name([], "deploy") == "deploy_1"
        assert (
            next_deploy_tag_name(["v1.0.0", "other"], "deploy") == "deploy_1"
        )

    def test_increments_max_for_prefix(self) -> None:
        """Higher numeric suffix wins; other prefixes are ignored."""

        tags = ["deploy_1", "deploy_3", "release_99", "deploy_2"]
        assert next_deploy_tag_name(tags, "deploy") == "deploy_4"

    def test_custom_prefix(self) -> None:
        """Only tags matching ``{prefix}_{N}`` affect sequencing."""

        tags = ["deploy_5", "ship_1", "ship_2"]
        assert next_deploy_tag_name(tags, "ship") == "ship_3"
