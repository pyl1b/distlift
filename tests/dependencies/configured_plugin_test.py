"""Tests for ConfiguredDependencyUpdaterPlugin."""

from pathlib import Path

from distlift.config.models import (
    DependencyUpdatesConfig,
    ExternalMonorepoDependencyUpdateConfig,
    Language,
    ManagedPackageConfig,
    MonorepoConfig,
    ReleaseMode,
    ResolvedConfig,
)
from distlift.dependencies.configured_plugin import (
    ConfiguredDependencyUpdaterPlugin,
    ExternalMonorepoDependencyUpdaterPlugin,
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

    def test_external_monorepo_plugin_updates_dependents(
        self, tmp_path: Path
    ) -> None:
        """Update dependents found in a configured external monorepo."""
        release_root = tmp_path / "release"
        (release_root / "packages" / "a").mkdir(parents=True)
        (release_root / "packages" / "a" / "pyproject.toml").write_text(
            '[project]\nname = "pkg-a"\nversion = "1.0.0"\n'
        )

        external_root = tmp_path / "external"
        (external_root / "packages" / "b").mkdir(parents=True)
        (external_root / "packages" / "b" / "pyproject.toml").write_text(
            '[project]\nname = "pkg-b"\nversion = "0.1.0"\n'
            'dependencies = ["pkg-a>=1.0.0"]\n'
        )
        (external_root / "distlift.toml").write_text(
            """
[release]
mode = "monorepo"
language = "python"

[[monorepo.packages]]
name = "b"
path = "packages/b"
"""
        )

        plugin = ExternalMonorepoDependencyUpdaterPlugin(
            name="external-plugin",
            version="0.1.0",
            external_monorepos=[
                ExternalMonorepoDependencyUpdateConfig(
                    path=str(external_root),
                    projects=["*"],
                )
            ],
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
                ],
            ),
            dependency_updates=DependencyUpdatesConfig(enabled=True),
        )
        request = DependencyUpdateRequest(
            repo_root=release_root,
            config=repo_config,
            plan=None,
            released_versions=[
                ReleasedProjectVersion(
                    package_name="a",
                    dependency_name="pkg-a",
                    version="1.2.0",
                    language=Language.PYTHON,
                    root=release_root / "packages" / "a",
                    manifest_path=release_root
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
            in (
                external_root / "packages" / "b" / "pyproject.toml"
            ).read_text()
        )

    def test_external_plugin_updates_simple_repo_frontend_dependency(
        self, tmp_path: Path
    ) -> None:
        """Update a package.json dependency in a simple external repo."""
        release_root = tmp_path / "release"
        (release_root / "packages" / "i18n").mkdir(parents=True)
        (release_root / "packages" / "i18n" / "package.json").write_text(
            '{\n  "name": "@advtslib/i18n",\n  "version": "0.1.0"\n}\n'
        )

        external_root = tmp_path / "external"
        (external_root / "backend").mkdir(parents=True)
        (external_root / "frontend").mkdir(parents=True)
        (external_root / "backend" / "pyproject.toml").write_text(
            '[project]\nname = "app-backend"\nversion = "0.1.0"\n'
        )
        (external_root / "frontend" / "package.json").write_text(
            "{\n"
            '  "name": "app-frontend",\n'
            '  "version": "0.1.0",\n'
            '  "dependencies": {\n'
            '    "@advtslib/i18n": "^0.1.0"\n'
            "  }\n"
            "}\n"
        )
        (external_root / "distlift.toml").write_text(
            """
mode = "simple"
version_source = "manifest"

[[version_files]]
path = "backend/pyproject.toml"
kind = "pyproject"
primary = true

[[version_files]]
path = "frontend/package.json"
kind = "package-json"
"""
        )

        plugin = ExternalMonorepoDependencyUpdaterPlugin(
            name="external-plugin",
            version="0.1.0",
            external_monorepos=[
                ExternalMonorepoDependencyUpdateConfig(
                    path=str(external_root),
                    projects=["*"],
                )
            ],
        )
        repo_config = ResolvedConfig(
            language=Language.JAVASCRIPT,
            mode=ReleaseMode.MONOREPO,
            remotes=[],
            monorepo=MonorepoConfig(
                enabled=True,
                packages=[
                    ManagedPackageConfig(
                        name="i18n",
                        path="packages/i18n",
                        language=Language.JAVASCRIPT,
                    ),
                ],
            ),
            dependency_updates=DependencyUpdatesConfig(
                enabled=True,
                javascript_version_template="^{version}",
            ),
        )
        request = DependencyUpdateRequest(
            repo_root=release_root,
            config=repo_config,
            plan=None,
            released_versions=[
                ReleasedProjectVersion(
                    package_name="i18n",
                    dependency_name="@advtslib/i18n",
                    version="1.2.0",
                    language=Language.JAVASCRIPT,
                    root=release_root / "packages" / "i18n",
                    manifest_path=release_root
                    / "packages"
                    / "i18n"
                    / "package.json",
                ),
            ],
            dry_run=False,
        )

        result = plugin.update_dependencies(request)

        assert result.changes
        assert (
            '"@advtslib/i18n": "^1.2.0"'
            in (external_root / "frontend" / "package.json").read_text()
        )
