"""Update Python dependency declarations in pyproject.toml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tomlkit
from packaging.requirements import Requirement

from distlift.dependencies.projects import normalize_python_dependency_name
from distlift.errors import ManifestUpdateError
from distlift.logging_utils import get_logger
from distlift.manifests.pyproject_file import read_pyproject

log = get_logger(__name__)


@dataclass(frozen=True)
class PythonDependencySpecLocation:
    """Location of one dependency string inside pyproject.toml.

    Attributes:
        section: ``dependencies`` or optional group name.
        index: Index within the dependency list.
        original: Original requirement string from the file.
    """

    section: str
    index: int
    original: str


def find_python_dependency_specs(
    path: Path, dependency_name: str
) -> list[PythonDependencySpecLocation]:
    """Find dependency requirement strings matching ``dependency_name``.

    Args:
        path: Path to ``pyproject.toml``.
        dependency_name: Distribution name to match (PEP 503 normalized).
    """
    data = read_pyproject(path)
    target = normalize_python_dependency_name(dependency_name)
    locations: list[PythonDependencySpecLocation] = []

    project = data.get("project", {})

    if not isinstance(project, dict):
        return locations

    deps = project.get("dependencies", [])

    if isinstance(deps, list):
        for i, item in enumerate(deps):
            if not isinstance(item, str):
                continue

            if _requirement_matches_name(item, target):
                locations.append(
                    PythonDependencySpecLocation(
                        section="dependencies",
                        index=i,
                        original=item,
                    )
                )

    optional = project.get("optional-dependencies", {})

    if isinstance(optional, dict):
        for group_name, group_deps in optional.items():
            if not isinstance(group_deps, list):
                continue

            for i, item in enumerate(group_deps):
                if not isinstance(item, str):
                    continue

                if _requirement_matches_name(item, target):
                    locations.append(
                        PythonDependencySpecLocation(
                            section=str(group_name),
                            index=i,
                            original=item,
                        )
                    )

    return locations


def update_python_dependency(
    path: Path,
    dependency_name: str,
    version_template: str,
    version: str,
    *,
    dry_run: bool,
) -> list[tuple[str, str]]:
    """Update matching Python dependencies and return old/new specifier pairs.

    Args:
        path: Path to ``pyproject.toml``.
        dependency_name: Distribution name to match.
        version_template: Template with ``{version}`` placeholder.
        version: Released version string.
        dry_run: When True, do not write the file.

    Returns:
        List of ``(old_specifier, new_specifier)`` tuples for each change.
    """
    locations = find_python_dependency_specs(path, dependency_name)

    if not locations:
        return []

    try:
        content = path.read_text(encoding="utf-8")
        doc = tomlkit.loads(content)
    except Exception as exc:
        raise ManifestUpdateError(f"Cannot read {path}: {exc}") from exc

    project = doc.get("project")

    if project is None:
        return []

    changes: list[tuple[str, str]] = []
    new_version_text = version_template.replace("{version}", version)

    for loc in locations:
        new_req_str = _build_requirement_string(
            loc.original, dependency_name, new_version_text
        )
        changes.append((loc.original, new_req_str))

        if dry_run:
            continue

        if loc.section == "dependencies":
            deps_table = project.get("dependencies")

            if isinstance(deps_table, list):
                deps_table[loc.index] = new_req_str
        else:
            optional = project.get("optional-dependencies")

            if isinstance(optional, dict):
                group = optional.get(loc.section)

                if isinstance(group, list):
                    group[loc.index] = new_req_str

    if not dry_run and changes:
        try:
            path.write_text(tomlkit.dumps(doc), encoding="utf-8")
        except Exception as exc:
            raise ManifestUpdateError(f"Cannot write {path}: {exc}") from exc

    return changes


def _requirement_matches_name(
    requirement_str: str, normalized_name: str
) -> bool:
    """Return True when ``requirement_str`` names the normalized distribution.

    Args:
        requirement_str: PEP 508 requirement string.
        normalized_name: PEP 503 normalized name to compare.
    """
    try:
        req = Requirement(requirement_str)
    except Exception as exc:
        log.log(
            1,
            "Skipping unparsable requirement %r: %s",
            requirement_str,
            exc,
            exc_info=True,
        )
        return False

    return normalize_python_dependency_name(req.name) == normalized_name


def _build_requirement_string(
    original: str, dependency_name: str, new_version_text: str
) -> str:
    """Rebuild a requirement string preserving extras and markers.

    Args:
        original: Original requirement string from the manifest.
        dependency_name: Distribution name for the dependency.
        new_version_text: Version specifier text (e.g. ``>=1.2.0``).
    """
    try:
        req = Requirement(original)
    except Exception:
        base_name = dependency_name
        extras_part = ""
        marker_part = ""
    else:
        base_name = req.name
        extras_part = f"[{','.join(sorted(req.extras))}]" if req.extras else ""
        marker_part = f"; {req.marker}" if req.marker else ""

    return f"{base_name}{extras_part}{new_version_text}{marker_part}"
