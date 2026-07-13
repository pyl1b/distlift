"""Tests for package manager plugin registry."""

from __future__ import annotations

from distlift.package_managers.npm import NpmPackageManagerPlugin
from distlift.package_managers.pip import PipPackageManagerPlugin
from distlift.plugins.registry import PluginRegistry


class TestPackageManagerRegistry:
    """Tests for package manager registration."""

    def test_register_and_lookup(self) -> None:
        registry = PluginRegistry()
        pip = PipPackageManagerPlugin()
        npm = NpmPackageManagerPlugin()
        registry.register_package_manager_plugin(pip, source="test")
        registry.register_package_manager_plugin(npm, source="test")
        assert registry.get_package_manager_plugin("pip") is pip
        assert len(registry.get_package_manager_plugins()) == 2
