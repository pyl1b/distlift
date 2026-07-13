"""Tests for interactive dependency upgrade execution."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from distlift.config.models import (
    DependencyUpgradesConfig,
    Language,
    ResolvedConfig,
)
from distlift.dependencies.models import (
    DependencyProject,
    DependencyUpdateChange,
)
from distlift.dependencies.upgrade_models import (
    DeclaredDependency,
    DependencySelection,
    DependencyUpgradePlan,
    PackageSource,
    PluginCommandResult,
    SourceUpgradePlan,
)
from distlift.dependencies.upgrade_service import execute_upgrade_plan


def _sample_plan(
    tmp_path: Path,
    *,
    install_packages: bool = True,
) -> DependencyUpgradePlan:
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text(
        """
[project]
name = "demo"
version = "0.1.0"
dependencies = ["attrs>=23.0"]
""".strip(),
        encoding="utf-8",
    )
    dep = DeclaredDependency(
        name="attrs",
        group="dependencies",
        constraint=">=23.0",
        location_key="k",
    )
    source = PackageSource(
        project=DependencyProject(
            name="demo",
            dependency_name="demo",
            language=Language.PYTHON,
            root=tmp_path,
            manifest_path=manifest,
        ),
        manager_name="pip",
    )
    selection = DependencySelection(
        dependency=dep,
        target_version="26.2.0",
    )
    return DependencyUpgradePlan(
        repo_root=tmp_path,
        sources=(
            SourceUpgradePlan(
                source=source,
                selections=(selection,),
                manifest_path=manifest,
                planned_changes=(
                    DependencyUpdateChange(
                        project_name="demo",
                        dependency_name="attrs",
                        manifest_path=manifest,
                        old_specifier=">=23.0",
                        new_specifier=">=26.2.0",
                    ),
                ),
            ),
        ),
        dry_run=False,
        install_packages=install_packages,
    )


class TestExecuteUpgradePlan:
    """Tests for upgrade plan execution branching."""

    def test_install_packages_when_enabled(self, tmp_path: Path) -> None:
        plugin = MagicMock()
        plugin.apply_manifest_updates.return_value = [
            DependencyUpdateChange(
                project_name="demo",
                dependency_name="attrs",
                manifest_path=tmp_path / "pyproject.toml",
                old_specifier=">=23.0",
                new_specifier=">=26.2.0",
            )
        ]
        plugin.install_packages.return_value = [
            PluginCommandResult(
                command=["python", "-m", "pip", "install", "attrs>=26.2.0"]
            )
        ]
        plugin.verify_upgrades.return_value = []
        registry = MagicMock()
        registry.get_package_manager_plugin.return_value = plugin
        config = ResolvedConfig(
            dependency_upgrades=DependencyUpgradesConfig(
                install_packages=True,
            )
        )

        result = execute_upgrade_plan(
            _sample_plan(tmp_path, install_packages=True),
            registry,
            config,
        )

        assert result.success
        plugin.install_packages.assert_called_once()
        plugin.refresh_lock_files.assert_not_called()
        assert result.source_results[0].packages_installed == [
            "python -m pip install attrs>=26.2.0"
        ]

    def test_refresh_lock_files_when_install_disabled(
        self,
        tmp_path: Path,
    ) -> None:
        plugin = MagicMock()
        plugin.apply_manifest_updates.return_value = [
            DependencyUpdateChange(
                project_name="demo",
                dependency_name="attrs",
                manifest_path=tmp_path / "pyproject.toml",
                old_specifier=">=23.0",
                new_specifier=">=26.2.0",
            )
        ]
        plugin.refresh_lock_files.return_value = []
        plugin.verify_upgrades.return_value = []
        registry = MagicMock()
        registry.get_package_manager_plugin.return_value = plugin
        config = ResolvedConfig(
            dependency_upgrades=DependencyUpgradesConfig(
                install_packages=False,
            )
        )

        result = execute_upgrade_plan(
            _sample_plan(tmp_path, install_packages=False),
            registry,
            config,
        )

        assert result.success
        plugin.install_packages.assert_not_called()
        plugin.refresh_lock_files.assert_called_once()
