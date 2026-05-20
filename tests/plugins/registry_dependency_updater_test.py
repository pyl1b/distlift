"""Tests for dependency updater plugin registration."""

import pytest

from distlift.dependencies.configured_plugin import (
    ConfiguredDependencyUpdaterPlugin,
)
from distlift.errors import PluginError
from distlift.plugins.registry import PluginRegistry


class TestRegistryDependencyUpdater:
    """Tests for PluginRegistry dependency updater slots."""

    def test_register_and_list(self, tmp_path) -> None:
        """Register a dependency updater and retrieve it."""
        config_path = tmp_path / "dependency-updater.toml"
        config_path.write_text("[dependency_updates]\nenabled = true\n")
        plugin = ConfiguredDependencyUpdaterPlugin.from_file(
            "test-updater", "0.1.0", config_path
        )
        registry = PluginRegistry(allow_override=False)
        registry.register_dependency_updater_plugin(plugin, source="test")

        updaters = registry.get_dependency_updater_plugins()

        assert len(updaters) == 1
        assert updaters[0].get_updater_name() == "test-updater"

    def test_duplicate_raises_without_override(self, tmp_path) -> None:
        """Reject duplicate updater names when overrides are disabled."""
        config_path = tmp_path / "dependency-updater.toml"
        config_path.write_text("[dependency_updates]\nenabled = true\n")
        plugin = ConfiguredDependencyUpdaterPlugin.from_file(
            "dup", "0.1.0", config_path
        )
        registry = PluginRegistry(allow_override=False)
        registry.register_dependency_updater_plugin(plugin, source="a")

        with pytest.raises(PluginError):
            registry.register_dependency_updater_plugin(plugin, source="b")
