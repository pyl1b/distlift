"""Resolve monorepo package declarations and manifest paths."""

from __future__ import annotations

from pathlib import Path

from distlift.config.models import ManagedPackageConfig, ResolvedConfig
from distlift.errors import ConfigurationError


def load_managed_packages(
    config: ResolvedConfig,
) -> list[ManagedPackageConfig]:
    """Load ``[[monorepo.packages]]`` entries from merged configuration.

    Args:
        config: Fully merged distlift configuration for the repository.

    Returns:
        A list copy of configured packages.

    Raises:
        ConfigurationError: When the packages table is empty.
    """
    packages = config.monorepo.packages

    if not packages:
        raise ConfigurationError(
            "Monorepo mode requires at least one [[monorepo.packages]] entry"
        )

    return list(packages)


def resolve_package_manifest_path(
    package: ManagedPackageConfig, repo_root: Path
) -> Path:
    """Resolve the manifest file used to read or write a package version.

    Args:
        package: Single managed package entry including path and language.
        repo_root: Absolute repository root used to anchor relative paths.

    Returns:
        Absolute ``pyproject.toml`` or ``package.json`` path for the package.
    """
    if package.manifest_path:
        return Path(package.manifest_path)

    pkg_root = repo_root / package.path
    lang = package.language

    if lang is not None and lang.value == "javascript":
        return pkg_root / "package.json"

    return pkg_root / "pyproject.toml"
