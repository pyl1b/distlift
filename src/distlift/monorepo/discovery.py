from __future__ import annotations

from pathlib import Path

from distlift.config.models import ManagedPackageConfig, ResolvedConfig
from distlift.errors import ConfigurationError


def load_managed_packages(
    config: ResolvedConfig,
) -> list[ManagedPackageConfig]:
    """Return the list of managed packages from config, validating each."""
    packages = config.monorepo.packages
    if not packages:
        raise ConfigurationError(
            "Monorepo mode requires at least one [[monorepo.packages]] entry"
        )
    return list(packages)


def resolve_package_manifest_path(
    package: ManagedPackageConfig, repo_root: Path
) -> Path:
    """Return the absolute path to the package manifest."""
    if package.manifest_path:
        return Path(package.manifest_path)
    pkg_root = repo_root / package.path
    lang = package.language
    if lang is not None and lang.value == "javascript":
        return pkg_root / "package.json"
    return pkg_root / "pyproject.toml"
