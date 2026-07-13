"""Version cycle helpers for the interactive dependency selector."""

from __future__ import annotations

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from distlift.dependencies.upgrade_models import (
    DependencyVersionChoice,
    RegistryVersion,
)


def latest_stable_version(
    versions: tuple[RegistryVersion, ...],
) -> str | None:
    """Return the newest non-yanked stable version when present.

    Args:
        versions: Registry versions ordered newest-first.
    """
    for entry in versions:
        if entry.is_yanked or entry.is_prerelease:
            continue

        return entry.version

    return None


def currently_used_version(choice: DependencyVersionChoice) -> Version:
    """Resolve the baseline version used for Space-cycle filtering.

    Args:
        choice: Registry data and manifest metadata for one dependency.
    """
    dep = choice.dependency

    if dep.resolved_version:
        try:
            return Version(dep.resolved_version)
        except Exception:
            pass

    if dep.installed_version:
        try:
            return Version(dep.installed_version)
        except Exception:
            pass

    minimum = _minimum_version_from_constraint(dep.constraint)

    if minimum is not None:
        return minimum

    return Version("0.0.0")


def build_version_cycle(
    choice: DependencyVersionChoice,
) -> list[str | None]:
    """Build the Space-cycle targets ending with ``None`` (do not update).

    Args:
        choice: Registry data and manifest metadata for one dependency.
    """
    if choice.lookup_error:
        return [None]

    baseline = currently_used_version(choice)
    latest = choice.latest_stable

    if latest is None and choice.available_versions:
        latest = choice.available_versions[0].version

    cycle: list[str | None] = []

    if latest is not None:
        try:
            if Version(latest) > baseline:
                cycle.append(latest)
        except Exception:
            cycle.append(latest)

    for entry in choice.available_versions:
        try:
            version_obj = Version(entry.version)
        except Exception:
            continue

        if version_obj <= baseline:
            continue

        if latest is not None and entry.version == latest:
            continue

        cycle.append(entry.version)

    cycle.append(None)

    if not cycle:
        return [None]

    return cycle


def has_available_upgrade(choice: DependencyVersionChoice) -> bool:
    """Return whether a dependency has any target newer than the baseline.

    Args:
        choice: Registry data and manifest metadata for one dependency.
    """
    cycle = build_version_cycle(choice)
    return any(version is not None for version in cycle)


def filter_upgradable_choices(
    choices: list[DependencyVersionChoice],
) -> list[DependencyVersionChoice]:
    """Return only dependencies that have at least one upgrade target.

    Args:
        choices: Registry-enriched dependency rows for one source.
    """
    return [choice for choice in choices if has_available_upgrade(choice)]


def selection_from_cycle_index(
    choice: DependencyVersionChoice,
    cycle_index: int,
) -> tuple[str | None, int]:
    """Return the target version and normalized index for one cycle state.

    Args:
        choice: Registry data for one dependency row.
        cycle_index: Index into the Space-cycle list.
    """
    cycle = build_version_cycle(choice)

    if not cycle:
        return None, 0

    normalized = cycle_index % len(cycle)
    return cycle[normalized], normalized


def toggle_stable_or_skip(
    choice: DependencyVersionChoice,
    current_index: int,
) -> tuple[str | None, int]:
    """Toggle between latest stable and do not update for Left/Right keys.

    Args:
        choice: Registry data for one dependency row.
        current_index: Current cycle index for the row.
    """
    cycle = build_version_cycle(choice)
    current_target, _ = selection_from_cycle_index(choice, current_index)

    if current_target is None:
        return selection_from_cycle_index(choice, 0)

    return selection_from_cycle_index(choice, len(cycle) - 1)


def _minimum_version_from_constraint(constraint: str) -> Version | None:
    """Parse the minimum version implied by one manifest constraint.

    Args:
        constraint: Raw specifier text from a manifest.
    """
    cleaned = constraint.strip()

    if cleaned.startswith(("^", "~", ">=", "<=", "==", ">", "<")):
        try:
            spec = SpecifierSet(cleaned.lstrip("^~"))
            versions = [Version(str(s)) for s in spec if str(s)]

            if versions:
                return min(versions)
        except Exception:
            pass

    if cleaned.startswith("^") or cleaned.startswith("~"):
        digits = cleaned[1:].split(".")
        parts = [int(p) for p in digits[:3] if p.isdigit()]

        while len(parts) < 3:
            parts.append(0)

        return Version(".".join(str(p) for p in parts))

    try:
        req = Requirement(f"pkg{constraint}")
        spec = req.specifier

        if not spec:
            return None

        versions = [Version(str(s)) for s in spec if str(s)]

        if versions:
            return min(versions)
    except Exception:
        pass

    bare = cleaned.split(",")[0].strip()

    try:
        return Version(bare)
    except Exception:
        return None
