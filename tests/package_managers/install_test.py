"""Tests for package manager environment install helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from distlift.config.models import DependencyUpgradesConfig, ResolvedConfig
from distlift.dependencies.upgrade_models import (
    DeclaredDependency,
    DependencySelection,
    PackageSource,
    PluginCommandResult,
)
from distlift.package_managers.base import (
    python_pip_requirement,
    verify_installed_package_versions,
)
from distlift.package_managers.pip import PipPackageManagerPlugin


class TestPythonPipRequirement:
    """Tests for pip requirement string formatting."""

    def test_joins_operator_specifiers(self) -> None:
        assert python_pip_requirement("attrs", ">=26.2.0") == "attrs>=26.2.0"


class TestVerifyInstalledPackageVersions:
    """Tests for installed-version verification."""

    def test_reports_missing_and_outdated_packages(self) -> None:
        selections = [
            DependencySelection(
                dependency=DeclaredDependency(
                    name="attrs",
                    group="dependencies",
                    constraint=">=23.0",
                    location_key="a",
                ),
                target_version="26.2.0",
            ),
            DependencySelection(
                dependency=DeclaredDependency(
                    name="tomlkit",
                    group="dependencies",
                    constraint=">=0.12",
                    location_key="b",
                ),
                target_version="0.13.3",
            ),
        ]
        errors = verify_installed_package_versions(
            {"attrs": "26.1.0"},
            selections,
        )
        assert "attrs installed as 26.1.0" in errors[0]
        assert "tomlkit not installed in environment" in errors[1]


class TestPipInstallPackages:
    """Tests for pip environment installs."""

    def test_install_packages_runs_pip_for_each_selection(
        self,
        tmp_path: Path,
    ) -> None:
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
        source = PackageSource(
            project=__import__(
                "distlift.dependencies.models",
                fromlist=["DependencyProject"],
            ).DependencyProject(
                name="demo",
                dependency_name="demo",
                language=__import__(
                    "distlift.config.models",
                    fromlist=["Language"],
                ).Language.PYTHON,
                root=tmp_path,
                manifest_path=manifest,
            ),
            manager_name="pip",
        )
        plugin = PipPackageManagerPlugin()
        selection = DependencySelection(
            dependency=DeclaredDependency(
                name="attrs",
                group="dependencies",
                constraint=">=23.0",
                location_key="k",
            ),
            target_version="26.2.0",
        )
        config = ResolvedConfig()

        with patch(
            "distlift.package_managers.pip.run_command",
            return_value=PluginCommandResult(
                command=["python", "-m", "pip", "install", "attrs>=26.2.0"],
                returncode=0,
            ),
        ) as run_command:
            results = plugin.install_packages(
                source,
                [selection],
                config,
                dry_run=False,
                timeout_seconds=30,
            )

        assert len(results) == 1
        cmd = run_command.call_args.args[0]
        assert cmd[-2:] == ["install", "attrs>=26.2.0"]

    def test_verify_upgrades_checks_installed_versions_when_enabled(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        manifest = tmp_path / "pyproject.toml"
        manifest.write_text(
            """
[project]
name = "demo"
version = "0.1.0"
dependencies = ["attrs>=26.2.0"]
""".strip(),
            encoding="utf-8",
        )
        from distlift.config.models import Language
        from distlift.dependencies.models import DependencyProject

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
        plugin = PipPackageManagerPlugin()
        selection = DependencySelection(
            dependency=DeclaredDependency(
                name="attrs",
                group="dependencies",
                constraint=">=26.2.0",
                location_key="k",
            ),
            target_version="26.2.0",
        )
        config = ResolvedConfig(
            dependency_upgrades=DependencyUpgradesConfig(
                install_packages=True,
            )
        )
        monkeypatch.setattr(
            plugin,
            "read_installed_versions",
            lambda _source: {"attrs": "26.1.0"},
        )

        errors = plugin.verify_upgrades(source, [selection], config)

        assert any("installed as 26.1.0" in error for error in errors)
