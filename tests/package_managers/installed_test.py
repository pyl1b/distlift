"""Tests for installed dependency version helpers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from distlift.package_managers.installed import (
    read_node_modules_installed_versions,
    read_python_installed_versions,
)


class TestReadPythonInstalledVersions:
    """Tests for Python environment version lookup."""

    def test_returns_installed_version_for_known_distribution(self) -> None:
        with patch(
            "importlib.metadata.version",
            return_value="3.0.52",
        ):
            versions = read_python_installed_versions(["prompt-toolkit"])

        assert versions == {"prompt-toolkit": "3.0.52"}

    def test_omits_missing_distributions(self) -> None:
        from importlib.metadata import PackageNotFoundError

        def _version(name: str) -> str:
            if name == "attrs":
                return "26.1.0"
            raise PackageNotFoundError(name)

        with patch("importlib.metadata.version", side_effect=_version):
            versions = read_python_installed_versions(["attrs", "missing-pkg"])

        assert versions == {"attrs": "26.1.0"}


class TestReadNodeModulesInstalledVersions:
    """Tests for node_modules version lookup."""

    def test_reads_direct_and_scoped_packages(self, tmp_path: Path) -> None:
        modules_root = tmp_path / "node_modules"
        react_dir = modules_root / "react"
        react_dir.mkdir(parents=True)
        (react_dir / "package.json").write_text(
            json.dumps({"name": "react", "version": "19.1.0"}),
            encoding="utf-8",
        )
        scoped_dir = modules_root / "@scope" / "pkg"
        scoped_dir.mkdir(parents=True)
        (scoped_dir / "package.json").write_text(
            json.dumps({"name": "@scope/pkg", "version": "2.0.0"}),
            encoding="utf-8",
        )

        versions = read_node_modules_installed_versions(
            tmp_path,
            ["react", "@scope/pkg", "missing"],
        )

        assert versions == {"react": "19.1.0", "@scope/pkg": "2.0.0"}

    def test_returns_empty_when_node_modules_missing(
        self, tmp_path: Path
    ) -> None:
        versions = read_node_modules_installed_versions(tmp_path, ["react"])
        assert versions == {}
