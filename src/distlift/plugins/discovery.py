"""Discover plugins from entry points, paths, and directories."""

from __future__ import annotations

import importlib.metadata
from collections.abc import Sequence
from pathlib import Path

import attrs

from distlift.constants import PLUGIN_ENTRY_POINT_GROUP
from distlift.logging_utils import get_logger

log = get_logger(__name__)


@attrs.define
class DiscoveredPlugin:
    """Description of a plugin candidate before it is imported.

    Attributes:
        name: Short name used in logs and load errors.
        source: Human-readable origin (entry point label or filesystem path).
        entry_point: Set when the plugin comes from ``importlib.metadata``.
        path: Set when the plugin is loaded from a file or package directory.
    """

    name: str
    source: str
    entry_point: importlib.metadata.EntryPoint | None = None
    path: Path | None = None


def discover_entry_point_plugins() -> list[DiscoveredPlugin]:
    """Return plugins under the ``distlift.plugins`` entry point group."""
    results: list[DiscoveredPlugin] = []

    try:
        eps = importlib.metadata.entry_points(group=PLUGIN_ENTRY_POINT_GROUP)
    except Exception as exc:
        log.warning("Entry point plugin discovery failed: %s", exc)
        return results

    for ep in eps:
        log.debug("Discovered entry point plugin: %s", ep.name)
        results.append(
            DiscoveredPlugin(
                name=ep.name,
                source=f"entry_point:{ep.name}",
                entry_point=ep,
            )
        )

    return results


def discover_plugins_from_paths(
    paths: Sequence[Path],
) -> list[DiscoveredPlugin]:
    """Build discovery records for explicit modules or package directories.

    Args:
        paths: Paths to ``.py`` files or dirs containing ``__init__.py``.
    """
    results: list[DiscoveredPlugin] = []

    for path in paths:
        path = path.resolve()

        if path.is_file() and path.suffix == ".py":
            results.append(
                DiscoveredPlugin(name=path.stem, source=str(path), path=path)
            )
        elif path.is_dir() and (path / "__init__.py").exists():
            results.append(
                DiscoveredPlugin(name=path.name, source=str(path), path=path)
            )
        else:
            log.warning(
                "Plugin path is not a .py file or Python package: %s", path
            )

    return results


def discover_plugins_from_directory(path: Path) -> list[DiscoveredPlugin]:
    """Scan one directory for importable plugin modules and packages.

    Args:
        path: Directory whose immediate children are considered.
    """
    path = path.resolve()

    if not path.is_dir():
        log.warning("Plugin directory does not exist: %s", path)
        return []

    results: list[DiscoveredPlugin] = []

    for item in sorted(path.iterdir()):
        if (
            item.is_file()
            and item.suffix == ".py"
            and not item.name.startswith("_")
        ):
            results.append(
                DiscoveredPlugin(name=item.stem, source=str(item), path=item)
            )
        elif item.is_dir() and (item / "__init__.py").exists():
            results.append(
                DiscoveredPlugin(name=item.name, source=str(item), path=item)
            )

    return results


def expand_plugin_directories(paths: Sequence[Path]) -> list[DiscoveredPlugin]:
    """Flatten a list of directories into all child plugin candidates.

    Args:
        paths: Root directories scanned for importable plugin modules.
    """
    results: list[DiscoveredPlugin] = []

    for path in paths:
        results.extend(discover_plugins_from_directory(path))

    return results
