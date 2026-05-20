"""Update JavaScript dependency declarations in package.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from distlift.errors import ManifestUpdateError
from distlift.manifests.package_json_file import read_package_json

_JS_DEP_GROUPS = (
    "dependencies",
    "devDependencies",
    "peerDependencies",
    "optionalDependencies",
)

_WORKSPACE_PREFIXES = ("workspace:*", "workspace:^")


@dataclass(frozen=True)
class JavascriptDependencySpecLocation:
    """Location of one dependency entry inside package.json.

    Attributes:
        group: Dependency group key (e.g. ``dependencies``).
        original: Original version or range string.
    """

    group: str
    original: str


def find_javascript_dependency_specs(
    path: Path, dependency_name: str
) -> list[JavascriptDependencySpecLocation]:
    """Find dependency entries matching ``dependency_name`` exactly.

    Args:
        path: Path to ``package.json``.
        dependency_name: npm package name (exact match, trimmed).
    """
    data = read_package_json(path)
    target = dependency_name.strip()
    locations: list[JavascriptDependencySpecLocation] = []

    for group in _JS_DEP_GROUPS:
        section = data.get(group)

        if not isinstance(section, dict):
            continue

        for pkg_name, spec in section.items():
            if str(pkg_name).strip() != target:
                continue

            if spec is None:
                continue

            locations.append(
                JavascriptDependencySpecLocation(
                    group=group,
                    original=str(spec),
                )
            )

    return locations


def update_javascript_dependency(
    path: Path,
    dependency_name: str,
    version_template: str,
    version: str,
    *,
    dry_run: bool,
) -> list[tuple[str, str]]:
    """Update matching JavaScript dependencies and return old/new pairs.

    Args:
        path: Path to ``package.json``.
        dependency_name: npm package name to match.
        version_template: Template with ``{version}`` placeholder.
        version: Released version string.
        dry_run: When True, do not write the file.

    Returns:
        List of ``(old_specifier, new_specifier)`` tuples for each change.
    """
    locations = find_javascript_dependency_specs(path, dependency_name)

    if not locations:
        return []

    try:
        content = path.read_text(encoding="utf-8")
        data: dict[str, Any] = json.loads(content)
    except Exception as exc:
        raise ManifestUpdateError(f"Cannot read {path}: {exc}") from exc

    new_spec = version_template.replace("{version}", version)
    changes: list[tuple[str, str]] = []
    target = dependency_name.strip()

    for group in _JS_DEP_GROUPS:
        section = data.get(group)

        if not isinstance(section, dict):
            continue

        if target not in section:
            continue

        old_val = str(section[target])
        new_val = _resolve_javascript_spec(old_val, new_spec)
        changes.append((old_val, new_val))

        if not dry_run:
            section[target] = new_val

    if not dry_run and changes:
        try:
            path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except Exception as exc:
            raise ManifestUpdateError(f"Cannot write {path}: {exc}") from exc

    return changes


def _resolve_javascript_spec(old_val: str, new_spec: str) -> str:
    """Map workspace protocols to the configured version template result.

    Args:
        old_val: Existing specifier from package.json.
        new_spec: Fully expanded new specifier string.
    """
    stripped = old_val.strip()

    for prefix in _WORKSPACE_PREFIXES:
        if stripped == prefix:
            return new_spec

    return new_spec
