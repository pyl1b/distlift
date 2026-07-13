"""List direct dependencies from supported manifest formats."""

from __future__ import annotations

from pathlib import Path

from packaging.requirements import Requirement

from distlift.dependencies.javascript import _WORKSPACE_PREFIXES, JS_DEP_GROUPS
from distlift.dependencies.projects import normalize_python_dependency_name
from distlift.dependencies.upgrade_models import DeclaredDependency
from distlift.manifests.package_json_file import read_package_json
from distlift.manifests.pyproject_file import read_pyproject


def list_python_dependencies(path: Path) -> list[DeclaredDependency]:
    """Enumerate PEP 621 dependencies declared in ``pyproject.toml``.

    Args:
        path: Path to the project manifest.
    """
    data = read_pyproject(path)
    project = data.get("project", {})
    results: list[DeclaredDependency] = []

    if not isinstance(project, dict):
        return results

    deps = project.get("dependencies", [])

    if isinstance(deps, list):
        for index, item in enumerate(deps):
            if not isinstance(item, str):
                continue

            name = _dependency_name_from_requirement(item)

            if name is None:
                continue

            results.append(
                DeclaredDependency(
                    name=name,
                    group="dependencies",
                    constraint=item,
                    location_key=f"{path}:dependencies:{index}",
                )
            )

    optional = project.get("optional-dependencies", {})

    if isinstance(optional, dict):
        for group_name, group_deps in optional.items():
            if not isinstance(group_deps, list):
                continue

            for index, item in enumerate(group_deps):
                if not isinstance(item, str):
                    continue

                name = _dependency_name_from_requirement(item)

                if name is None:
                    continue

                results.append(
                    DeclaredDependency(
                        name=name,
                        group=str(group_name),
                        constraint=item,
                        location_key=(f"{path}:optional:{group_name}:{index}"),
                    )
                )

    return results


def list_javascript_dependencies(path: Path) -> list[DeclaredDependency]:
    """Enumerate npm-style dependencies declared in ``package.json``.

    Args:
        path: Path to the project manifest.
    """
    data = read_package_json(path)
    results: list[DeclaredDependency] = []

    for group in JS_DEP_GROUPS:
        section = data.get(group)

        if not isinstance(section, dict):
            continue

        for pkg_name, spec in section.items():
            if spec is None:
                continue

            constraint = str(spec)
            stripped = constraint.strip()
            is_workspace = any(
                stripped == prefix for prefix in _WORKSPACE_PREFIXES
            )

            results.append(
                DeclaredDependency(
                    name=str(pkg_name).strip(),
                    group=group,
                    constraint=constraint,
                    location_key=f"{path}:{group}:{pkg_name}",
                    is_workspace=is_workspace,
                )
            )

    return results


def _dependency_name_from_requirement(requirement_str: str) -> str | None:
    """Return the distribution name from one PEP 508 requirement string.

    Args:
        requirement_str: Requirement text from a manifest dependency list.
    """
    try:
        req = Requirement(requirement_str)
    except Exception:
        return None

    return normalize_python_dependency_name(req.name)
