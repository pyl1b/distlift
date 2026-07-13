"""Package manager detection for interactive dependency upgrades."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from distlift.dependencies.models import DependencyProject
from distlift.dependencies.upgrade_models import PackageSource
from distlift.errors import PackageManagerDetectionError
from distlift.manifests.package_json_file import read_package_json
from distlift.package_managers.base import manager_from_package_manager_field

if TYPE_CHECKING:
    from distlift.config.models import DependencyUpgradesConfig
    from distlift.plugins.registry import PluginRegistry

_JS_LOCK_FILES = {
    "package-lock.json": "npm",
    "pnpm-lock.yaml": "pnpm",
    "yarn.lock": "yarn",
}


def detect_package_source(
    project: DependencyProject,
    registry: PluginRegistry,
    *,
    manager_overrides: dict[str, str] | None = None,
    upgrades_config: DependencyUpgradesConfig | None = None,
) -> PackageSource:
    """Select the package manager plugin that owns one dependency project.

    Args:
        project: Candidate dependency project.
        registry: Plugin registry with package manager plugins.
        manager_overrides: Optional per-project manager overrides.
        upgrades_config: Optional dependency upgrade configuration.

    Raises:
        PackageManagerDetectionError: When detection is ambiguous or fails.
    """
    overrides = manager_overrides or {}
    config_overrides = {}

    if upgrades_config is not None:
        config_overrides = dict(upgrades_config.package_managers)

    override_name = overrides.get(project.name) or config_overrides.get(
        project.name
    )

    if override_name is None:
        _raise_on_ambiguous_js_locks(project)

    plugins = registry.get_package_manager_plugins()

    for plugin in plugins:
        if (
            override_name is not None
            and plugin.get_manager_name() != override_name
        ):
            continue

        source = plugin.detect_source(project, override_name=override_name)

        if source is not None:
            return source

    if override_name is not None:
        raise PackageManagerDetectionError(
            f"No package manager plugin registered for override {override_name!r}"
        )

    raise PackageManagerDetectionError(
        f"Could not detect package manager for project {project.name!r}"
    )


def _raise_on_ambiguous_js_locks(project: DependencyProject) -> None:
    """Raise when multiple JavaScript lock files are present.

    Args:
        project: Candidate dependency project.
    """
    root = project.root
    present = [name for name in _JS_LOCK_FILES if (root / name).is_file()]

    if len(present) <= 1:
        return

    pm_field = _read_package_manager_field(root)
    resolved = manager_from_package_manager_field(pm_field)

    if resolved is not None:
        return

    raise PackageManagerDetectionError(
        "Multiple lock files found in {}: {}; set --package-manager or "
        "[dependency_upgrades.package_managers]".format(
            project.name,
            ", ".join(present),
        )
    )


def _read_package_manager_field(root: Path) -> str | None:
    """Read ``packageManager`` from ``package.json`` when available.

    Args:
        root: JavaScript project root directory.
    """
    manifest = root / "package.json"

    if not manifest.is_file():
        return None

    data = read_package_json(manifest)
    value = data.get("packageManager")

    if value is None:
        return None

    return str(value).strip() or None
