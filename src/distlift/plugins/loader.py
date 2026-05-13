from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Sequence

from distlift.errors import PluginError
from distlift.logging_utils import get_logger
from distlift.plugins.base import DistliftPlugin
from distlift.plugins.discovery import DiscoveredPlugin

log = get_logger(__name__)


def load_plugin_module_from_path(path: Path) -> ModuleType:
    """Import a plugin module from a .py file or package directory."""
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
        raise PluginError(f"Failed to load plugin module from {path}: {exc}") from exc
    return module


def load_discovered_plugin(candidate: DiscoveredPlugin) -> DistliftPlugin:
    """Instantiate a DistliftPlugin from a DiscoveredPlugin descriptor."""
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
            f"DiscoveredPlugin '{candidate.name}' has neither entry_point nor path"
        )

    if callable(factory) and not isinstance(factory, type):
        instance = factory()
    elif isinstance(factory, type) and issubclass(factory, DistliftPlugin):
        instance = factory()
    else:
        raise PluginError(
            f"Plugin '{candidate.name}' factory must be a DistliftPlugin subclass or callable"
        )

    if not isinstance(instance, DistliftPlugin):
        raise PluginError(
            f"Plugin '{candidate.name}' factory returned {type(instance)!r},"
            " expected a DistliftPlugin"
        )
    return instance


def _find_plugin_factory(module: ModuleType, name: str) -> object:
    """Look for a get_plugin() function or a Plugin class in the module."""
    if hasattr(module, "get_plugin"):
        return module.get_plugin  # type: ignore[no-any-return]
    # Try to find a class named Plugin or matching the module name
    for attr_name in ("Plugin", name.title().replace("_", "") + "Plugin"):
        obj = getattr(module, attr_name, None)
        if (
            obj is not None
            and isinstance(obj, type)
            and issubclass(obj, DistliftPlugin)
        ):
            return obj
    raise PluginError(
        f"Plugin module '{module.__name__}' must define get_plugin() or a Plugin class"
    )


def load_plugins(candidates: Sequence[DiscoveredPlugin]) -> list[DistliftPlugin]:
    """Load all candidates, logging and skipping failures."""
    results: list[DistliftPlugin] = []
    for candidate in candidates:
        try:
            plugin = load_discovered_plugin(candidate)
            log.debug("Loaded plugin '%s' from %s", plugin.get_name(), candidate.source)
            results.append(plugin)
        except PluginError as exc:
            log.warning("Skipping plugin '%s': %s", candidate.name, exc)
    return results
