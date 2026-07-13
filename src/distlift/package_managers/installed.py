"""Resolve currently installed dependency versions."""

from __future__ import annotations

import json
from pathlib import Path

from distlift.dependencies.projects import normalize_python_dependency_name
from distlift.logging_utils import get_logger

log = get_logger(__name__)


def read_python_installed_versions(
    dependency_names: list[str],
) -> dict[str, str]:
    """Return installed versions from the active Python environment.

    Args:
        dependency_names: Declared distribution names to look up.
    """
    from importlib.metadata import PackageNotFoundError, version

    installed: dict[str, str] = {}

    for name in dependency_names:
        candidates = _python_lookup_names(name)

        for candidate in candidates:
            try:
                installed[name] = version(candidate)
                break
            except PackageNotFoundError:
                log.log(
                    1,
                    "Distribution %r not installed when resolving %s",
                    candidate,
                    name,
                )

    return installed


def read_node_modules_installed_versions(
    project_root: Path,
    dependency_names: list[str],
) -> dict[str, str]:
    """Return installed versions from a project's ``node_modules`` tree.

    Args:
        project_root: JavaScript project root directory.
        dependency_names: Declared npm package names to look up.
    """
    installed: dict[str, str] = {}
    modules_root = project_root / "node_modules"

    if not modules_root.is_dir():
        return installed

    for name in dependency_names:
        package_json = _node_modules_package_json(modules_root, name)

        if package_json is None:
            log.log(1, "No node_modules entry found for %s", name)
            continue

        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except Exception as exc:
            log.log(
                1,
                "Could not read %s for installed version: %s",
                package_json,
                exc,
                exc_info=True,
            )
            continue

        pkg_version = data.get("version")

        if pkg_version:
            installed[name] = str(pkg_version)

    return installed


def _python_lookup_names(dependency_name: str) -> list[str]:
    """Return candidate distribution names for one declared dependency.

    Args:
        dependency_name: Name from the project manifest.
    """
    normalized = normalize_python_dependency_name(dependency_name)
    candidates = [dependency_name]

    if normalized not in candidates:
        candidates.append(normalized)

    underscored = normalized.replace("-", "_")

    if underscored not in candidates:
        candidates.append(underscored)

    return candidates


def _node_modules_package_json(
    modules_root: Path,
    package_name: str,
) -> Path | None:
    """Return the ``package.json`` path for one installed npm package.

    Args:
        modules_root: Project ``node_modules`` directory.
        package_name: Declared npm package name.
    """
    if package_name.startswith("@"):
        path = modules_root / package_name / "package.json"
        return path if path.is_file() else None

    direct = modules_root / package_name / "package.json"

    if direct.is_file():
        return direct

    return None
