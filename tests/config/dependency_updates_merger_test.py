"""Tests for dependency_updates configuration merging."""

from distlift.config.merger import merge_config_layers
from distlift.config.models import (
    DependencyUpdateRule,
    DependencyUpdatesConfig,
    RawConfig,
)


class TestDependencyUpdatesMerger:
    """Tests for merging dependency_updates across layers."""

    def test_later_layer_rules_replace(self) -> None:
        """Take rules entirely from the highest-precedence non-empty layer."""
        layer1 = RawConfig(
            dependency_updates=DependencyUpdatesConfig(
                rules=[DependencyUpdateRule(package="a", projects=["b"])],
            ),
            source="low",
        )
        layer2 = RawConfig(
            dependency_updates=DependencyUpdatesConfig(
                rules=[DependencyUpdateRule(package="x", projects=["y"])],
            ),
            source="high",
        )

        config = merge_config_layers([layer1, layer2])

        assert len(config.dependency_updates.rules) == 1
        assert config.dependency_updates.rules[0].package == "x"
