"""Tests for ConfiguredDependencyUpdaterPlugin."""

from pathlib import Path

from distlift.config.models import (
    DependencyUpdatesConfig,
    Language,
    ManagedPackageConfig,
    MonorepoConfig,
    ReleaseMode,
    ResolvedConfig,
)
from distlift.dependencies.configured_plugin import (
    ConfiguredDependencyUpdaterPlugin,
)
from distlift.dependencies.models import (
    DependencyUpdateRequest,
    ReleasedProjectVersion,
)
from distlift.plugins.manager import PluginLoadRequest, PluginManager


class TestConfiguredDependencyUpdaterPlugin:
    """Tests for TOML-backed dependency updater plugins."""

    def test_from_file_applies_rules(self, tmp_path: Path) -> None:
        """Update dependents listed in the plugin TOML rules file."""
        (tmp_path / "packages" / "a").mkdir(parents=True)
        (tmp_path / "packages" / "b").mkdir(parents=True)
        (tmp_path / "packages" / "a" / "pyproject.toml").write_text(
            '[project]\nname = "pkg-a"\nversion = "1.0.0"\n'
        )
        (tmp_path / "packages" / "b" / "pyproject.toml").write_text(
            '[project]\nname = "pkg-b"\nversion = "0.1.0"\n'
            'dependencies = ["pkg-a>=1.0.0"]\n'
        )
        config_path = tmp_path / "dependency-updater.toml"
        config_path.write_text(
            """
[dependency_updates]
enabled = true

[[dependency_updates.rules]]
package = "a"
projects = ["b"]
"""
        )
        plugin = ConfiguredDependencyUpdaterPlugin.from_file(
            "test-plugin", "0.1.0", config_path
        )
        repo_config = ResolvedConfig(
            language=Language.PYTHON,
            mode=ReleaseMode.MONOREPO,
            remotes=[],
            monorepo=MonorepoConfig(
                enabled=True,
                packages=[
                    ManagedPackageConfig(
                        name="a",
                        path="packages/a",
                        language=Language.PYTHON,
                    ),
                    ManagedPackageConfig(
                        name="b",
                        path="packages/b",
                        language=Language.PYTHON,
                    ),
                ],
            ),
            dependency_updates=DependencyUpdatesConfig(enabled=False),
        )
        request = DependencyUpdateRequest(
            repo_root=tmp_path,
            config=repo_config,
            plan=None,
            released_versions=[
                ReleasedProjectVersion(
                    package_name="a",
                    dependency_name="pkg-a",
                    version="1.2.0",
                    language=Language.PYTHON,
                    root=tmp_path / "packages" / "a",
                    manifest_path=tmp_path
                    / "packages"
                    / "a"
                    / "pyproject.toml",
                ),
            ],
            dry_run=False,
        )

        result = plugin.update_dependencies(request)

        assert result.changes
        assert (
            "pkg-a>=1.2.0"
            in (tmp_path / "packages" / "b" / "pyproject.toml").read_text()
        )

    def test_registers_on_registry(self, tmp_path: Path) -> None:
        """Plugin register() adds a dependency updater to the registry."""
        config_path = tmp_path / "dependency-updater.toml"
        config_path.write_text("[dependency_updates]\nenabled = true\n")
        plugin = ConfiguredDependencyUpdaterPlugin.from_file(
            "reg-plugin", "0.1.0", config_path
        )
        manager = PluginManager()
        registry = manager.build_registry(
            PluginLoadRequest(disable_environment_plugins=True)
        )
        plugin.register(registry)

        names = [
            p.get_updater_name()
            for p in registry.get_dependency_updater_plugins()
        ]

        assert "reg-plugin" in names
