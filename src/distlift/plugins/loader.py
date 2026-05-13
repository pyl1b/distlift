"""Import plugin modules from disk and build ``DistliftPlugin`` objects."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

from distlift.errors import PluginError
from distlift.logging_utils import get_logger
from distlift.plugins.base import DistliftPlugin
from distlift.plugins.discovery import DiscoveredPlugin

log = get_logger(__name__)


def load_plugin_module_from_path(path: Path) -> ModuleType:
    """Import a plugin module from a ``.py`` file or package directory.

    Args:
        path: ``.py`` file path or directory that contains ``__init__.py``.
    """
    path = path.resolve()

    if path.is_dir():
        init = path / "__init__.py"
        if not init.exists():
            raise PluginError(f"Plugin directory has no __init__.py: {path}")
        module_name = f"distlift._ext_plugin_{path.name}"
        if path.parent not in sys.path:
            sys.path.insert(0, str(path.parent))
        spec = importlib.util.spec_from_file_location(module_name, init)
    else:
        module_name = f"distlift._ext_plugin_{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)

    if spec is None or spec.loader is None:
        raise PluginError(f"Cannot create module spec for plugin: {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as exc:
        raise PluginError(
            f"Failed to load plugin module from {path}: {exc}"
        ) from exc

    return module


def load_discovered_plugin(candidate: DiscoveredPlugin) -> DistliftPlugin:
    """Instantiate a ``DistliftPlugin`` from a discovery record.

    Args:
        candidate: Descriptor with either ``entry_point`` or ``path`` set.
    """
    if candidate.entry_point is not None:
        try:
            factory = candidate.entry_point.load()
        except Exception as exc:
            raise PluginError(
                f"Failed to load entry point plugin '{candidate.name}': {exc}"
            ) from exc
    elif candidate.path is not None:
        module = load_plugin_module_from_path(candidate.path)
        factory = _find_plugin_factory(module, candidate.name)
    else:
        raise PluginError(
            f"DiscoveredPlugin {candidate.name!r} has neither "
            "entry_point nor path"
        )

    if callable(factory) and not isinstance(factory, type):
        instance = factory()
    elif isinstance(factory, type) and issubclass(factory, DistliftPlugin):
        instance = factory()
    else:
        raise PluginError(
            f"Plugin {candidate.name!r} factory must be a DistliftPlugin "
            "subclass or callable"
        )

    if not isinstance(instance, DistliftPlugin):
        raise PluginError(
            f"Plugin '{candidate.name}' factory returned {type(instance)!r},"
            " expected a DistliftPlugin"
        )

    return instance


def _find_plugin_factory(module: ModuleType, name: str) -> object:
    """Resolve ``get_plugin`` or a ``DistliftPlugin`` subclass from ``module``.

    Args:
        module: Imported plugin module.
        name: Plugin short name derived from the file or package path.
    """
    if hasattr(module, "get_plugin"):
        return module.get_plugin  # type: ignore[no-any-return]

    for attr_name in ("Plugin", name.title().replace("_", "") + "Plugin"):
        obj = getattr(module, attr_name, None)
        if (
            obj is not None
            and isinstance(obj, type)
            and issubclass(obj, DistliftPlugin)
        ):
            return obj

    raise PluginError(
        f"Plugin module {module.__name__!r} must define get_plugin() "
        "or a Plugin class"
    )


def load_plugins(
    candidates: Sequence[DiscoveredPlugin],
) -> list[DistliftPlugin]:
    """Load each candidate, skipping entries that raise ``PluginError``.

    Args:
        candidates: Discovery records to attempt to load.
    """
    results: list[DistliftPlugin] = []

    for candidate in candidates:
        try:
            plugin = load_discovered_plugin(candidate)
            log.debug(
                "Loaded plugin '%s' from %s",
                plugin.get_name(),
                candidate.source,
            )
            results.append(plugin)
        except PluginError as exc:
            log.warning("Skipping plugin '%s': %s", candidate.name, exc)

    return results
