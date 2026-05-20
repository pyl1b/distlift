"""Tests for discovering and loading dependency updater plugins."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from distlift.dependencies.configured_plugin import (
    ConfiguredDependencyUpdaterPlugin,
)
from distlift.plugins.discovery import (
    discover_plugins_from_directory,
    discover_plugins_from_paths,
)
from distlift.plugins.loader import load_discovered_plugin
from distlift.plugins.manager import PluginLoadRequest, PluginManager
from distlift.plugins.scaffold import (
    DependencyUpdaterTemplateOptions,
    create_dependency_updater_plugin,
)


class TestDependencyUpdaterDiscovery:
    """Tests for loading scaffolded dependency updater plugins."""

    def test_load_via_plugin_directory_scan(self, tmp_path: Path) -> None:
        """Discover a plugin package under [plugins].directories layout."""
        out = tmp_path / "my-updater"
        create_dependency_updater_plugin(
            DependencyUpdaterTemplateOptions(
                name="my-updater",
                output_dir=out,
                rules=[],
                external_monorepos=[],
            )
        )
        discovered = discover_plugins_from_directory(out)

        assert any(d.name == "my_updater" for d in discovered)

        candidate = next(d for d in discovered if d.name == "my_updater")
        plugin = load_discovered_plugin(candidate)

        assert isinstance(plugin, ConfiguredDependencyUpdaterPlugin)
        assert plugin.get_updater_name() == "my-updater"

    def test_load_via_explicit_plugin_path(self, tmp_path: Path) -> None:
        """Load get_plugin from an explicit plugin module path."""
        out = tmp_path / "plugin"
        create_dependency_updater_plugin(
            DependencyUpdaterTemplateOptions(
                name="path-updater",
                output_dir=out,
                rules=[],
                external_monorepos=[],
            )
        )
        plugin_py = out / "path_updater" / "plugin.py"
        discovered = discover_plugins_from_paths([plugin_py])

        assert len(discovered) == 1
        plugin = load_discovered_plugin(discovered[0])

        assert isinstance(plugin, ConfiguredDependencyUpdaterPlugin)

    def test_registry_via_plugin_directories_config(
        self, tmp_path: Path
    ) -> None:
        """PluginManager picks up directory-scanned dependency updaters."""
        out = tmp_path / "dir-plugin"
        create_dependency_updater_plugin(
            DependencyUpdaterTemplateOptions(
                name="dir-updater",
                output_dir=out,
                rules=[],
                external_monorepos=[],
            )
        )
        manager = PluginManager()
        registry = manager.build_registry(
            PluginLoadRequest(
                plugin_directories=[out],
                disable_environment_plugins=True,
                disable_builtin_plugins=True,
            )
        )

        updaters = registry.get_dependency_updater_plugins()

        assert any(u.get_updater_name() == "dir-updater" for u in updaters)

    def test_load_via_editable_install_entry_point(
        self, tmp_path: Path
    ) -> None:
        """Entry-point metadata loads a pip editable-installed plugin."""
        out = tmp_path / "ep-plugin"
        create_dependency_updater_plugin(
            DependencyUpdaterTemplateOptions(
                name="ep-updater",
                output_dir=out,
                rules=[],
                external_monorepos=[],
            )
        )
        script = f"""
import importlib.metadata
import subprocess
import sys

from distlift.dependencies.configured_plugin import (
    ConfiguredDependencyUpdaterPlugin,
)
from distlift.plugins.discovery import DiscoveredPlugin
from distlift.plugins.loader import load_discovered_plugin

subprocess.run(
    [
        sys.executable,
        "-m",
        "pip",
        "uninstall",
        "-y",
        "distlift-ep-updater-dependency-updater",
    ],
    check=False,
    capture_output=True,
)
install = subprocess.run(
    [sys.executable, "-m", "pip", "install", "-e", {str(out)!r}],
    capture_output=True,
    text=True,
)
if install.returncode != 0:
    raise SystemExit(install.stderr)
entry_map = {{
    ep.name: ep
    for ep in importlib.metadata.entry_points(group="distlift.plugins")
}}
if "ep_updater" not in entry_map:
    raise SystemExit("ep_updater entry point not registered")
candidate = DiscoveredPlugin(
    name="ep_updater",
    source="entry_point:ep_updater",
    entry_point=entry_map["ep_updater"],
)
plugin = load_discovered_plugin(candidate)
if not isinstance(plugin, ConfiguredDependencyUpdaterPlugin):
    raise SystemExit("plugin type mismatch")
if plugin.get_updater_name() != "ep-updater":
    raise SystemExit("unexpected updater name")
subprocess.run(
    [
        sys.executable,
        "-m",
        "pip",
        "uninstall",
        "-y",
        "distlift-ep-updater-dependency-updater",
    ],
    check=False,
    capture_output=True,
)
"""
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
