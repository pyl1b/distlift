"""Tests for package manager detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from distlift.config.models import Language
from distlift.dependencies.models import DependencyProject
from distlift.errors import PackageManagerDetectionError
from distlift.package_managers.detection import detect_package_source
from distlift.plugins.manager import PluginLoadRequest, PluginManager


def _registry():
    manager = PluginManager()
    return manager.build_registry(
        PluginLoadRequest(
            disable_environment_plugins=True,
            disable_builtin_plugins=False,
        )
    )


class TestDetectPackageSource:
    """Tests for package manager detection."""

    def test_detects_pip_for_python_project(self, tmp_path: Path) -> None:
        manifest = tmp_path / "pyproject.toml"
        manifest.write_text(
            '[project]\nname="backend"\nversion="1.0.0"\n',
            encoding="utf-8",
        )
        project = DependencyProject(
            name="backend",
            dependency_name="backend",
            language=Language.PYTHON,
            root=tmp_path,
            manifest_path=manifest,
        )
        source = detect_package_source(project, _registry())
        assert source.manager_name == "pip"

    def test_detects_npm_from_package_lock(self, tmp_path: Path) -> None:
        manifest = tmp_path / "package.json"
        manifest.write_text(
            '{"name":"frontend","version":"1.0.0"}',
            encoding="utf-8",
        )
        (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
        project = DependencyProject(
            name="frontend",
            dependency_name="frontend",
            language=Language.JAVASCRIPT,
            root=tmp_path,
            manifest_path=manifest,
        )
        source = detect_package_source(project, _registry())
        assert source.manager_name == "npm"

    def test_ambiguous_lock_files_raise(self, tmp_path: Path) -> None:
        manifest = tmp_path / "package.json"
        manifest.write_text(
            '{"name":"frontend","version":"1.0.0"}',
            encoding="utf-8",
        )
        (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
        (tmp_path / "pnpm-lock.yaml").write_text(
            "lockfileVersion: 5\n", encoding="utf-8"
        )
        project = DependencyProject(
            name="frontend",
            dependency_name="frontend",
            language=Language.JAVASCRIPT,
            root=tmp_path,
            manifest_path=manifest,
        )
        with pytest.raises(PackageManagerDetectionError):
            detect_package_source(project, _registry())
