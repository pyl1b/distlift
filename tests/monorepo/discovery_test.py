from pathlib import Path

import pytest

from distlift.config.models import (
    Language,
    ManagedPackageConfig,
    MonorepoConfig,
    ReleaseMode,
    ResolvedConfig,
    VersionFormat,
    VersionSource,
)
from distlift.errors import ConfigurationError
from distlift.monorepo.discovery import (
    load_managed_packages,
    resolve_package_manifest_path,
)


def _config_with_packages(packages: list) -> ResolvedConfig:
    return ResolvedConfig(
        mode=ReleaseMode.MONOREPO,
        default_version="0.1.0",
        version_format=VersionFormat.MAJOR_MINOR_PATCH,
        remotes=["origin"],
        tag_template="v{version}",
        monorepo=MonorepoConfig(enabled=True, packages=packages),
    )


class TestLoadManagedPackages:
    def test_returns_packages(self):
        pkg = ManagedPackageConfig(name="lib", path="packages/lib")
        config = _config_with_packages([pkg])
        result = load_managed_packages(config)
        assert len(result) == 1
        assert result[0].name == "lib"

    def test_raises_when_empty(self):
        config = _config_with_packages([])
        with pytest.raises(ConfigurationError):
            load_managed_packages(config)


class TestResolvePackageManifestPath:
    def test_uses_explicit_manifest_path(self, tmp_path: Path):
        pkg = ManagedPackageConfig(
            name="lib",
            path="packages/lib",
            manifest_path="/some/path/pyproject.toml",
        )
        result = resolve_package_manifest_path(pkg, tmp_path)
        assert result == Path("/some/path/pyproject.toml")

    def test_default_python(self, tmp_path: Path):
        pkg = ManagedPackageConfig(
            name="lib", path="packages/lib", language=Language.PYTHON
        )
        result = resolve_package_manifest_path(pkg, tmp_path)
        assert result.name == "pyproject.toml"

    def test_default_javascript(self, tmp_path: Path):
        pkg = ManagedPackageConfig(
            name="lib", path="packages/lib", language=Language.JAVASCRIPT
        )
        result = resolve_package_manifest_path(pkg, tmp_path)
        assert result.name == "package.json"
