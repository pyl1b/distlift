"""Load raw configuration fragments from TOML files and environment."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from distlift.config.models import (
    Language,
    ManagedPackageConfig,
    MonorepoConfig,
    PluginConfig,
    RawConfig,
    ReleaseMode,
    VersionFormat,
    VersionSource,
)
from distlift.constants import ENV_PREFIX, PYPROJECT_TOOL_KEY


def load_toml_config(path: Path) -> dict[str, Any]:
    """Parse a TOML file into a plain dictionary structure.

    Args:
        path: Absolute or relative path to the TOML file on disk.
    """
    with path.open("rb") as fh:
        return tomllib.load(fh)


def load_pyproject_tool_config(path: Path) -> dict[str, Any]:
    """Return the ``[tool.distlift]`` table from a pyproject.toml file.

    Args:
        path: Path to the repository ``pyproject.toml`` document.
    """
    data = load_toml_config(path)

    return data.get("tool", {}).get(PYPROJECT_TOOL_KEY, {})


def load_environment_config(
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build a raw config dict from ``DISTLIFT_*`` environment variables.

    Args:
        env: Optional mapping to read instead of ``os.environ``.
    """
    if env is None:
        env = os.environ

    result: dict[str, Any] = {}

    def _get(key: str) -> str | None:
        """Return the value for ``DISTLIFT_<key>`` when present.

        Args:
            key: Suffix after the ``DISTLIFT_`` prefix, without that prefix.
        """
        return env.get(ENV_PREFIX + key)

    if v := _get("LANGUAGE"):
        result["language"] = v

    if v := _get("MODE"):
        result["mode"] = v

    if v := _get("DEFAULT_VERSION"):
        result["default_version"] = v

    if v := _get("VERSION_FORMAT"):
        result["version_format"] = v

    if v := _get("REMOTES"):
        result["remotes"] = [r.strip() for r in v.split(",") if r.strip()]

    if v := _get("TAG_TEMPLATE"):
        result["tag_template"] = v

    if v := _get("VERSION_SOURCE"):
        result["version_source"] = v

    if v := _get("MANIFEST_PATH"):
        result["manifest_path"] = v

    # Collect optional plugin-related environment overrides
    plugins: dict[str, Any] = {}

    if v := _get("PLUGIN_PATHS"):
        plugins["paths"] = [p.strip() for p in v.split(",") if p.strip()]

    if v := _get("PLUGIN_DIRS"):
        plugins["directories"] = [d.strip() for d in v.split(",") if d.strip()]

    if v := _get("ENABLE_ENVIRONMENT_PLUGINS"):
        plugins["enable_environment"] = v.lower() in ("1", "true", "yes")

    if v := _get("ENABLE_BUILTIN_PLUGINS"):
        plugins["enable_builtin"] = v.lower() in ("1", "true", "yes")

    if plugins:
        result["plugins"] = plugins

    return result


def _parse_raw_config(data: dict[str, Any], source: str) -> RawConfig:
    """Convert a loose config mapping into a structured ``RawConfig``.

    Args:
        data: Parsed TOML or environment-derived mapping for one layer.
        source: Human-readable label describing this layer's origin.
    """
    release = data.get("release", data)

    def _opt_enum(cls: type, key: str) -> Any:
        """Parse an optional string field into an enum member when valid.

        Args:
            cls: Enum class whose ``value`` strings match stored text.
            key: Key under the effective ``release`` mapping to read.
        """
        val = release.get(key)

        if val is None:
            return None

        try:
            return cls(val)
        except ValueError:
            return None

    language = _opt_enum(Language, "language")
    mode = _opt_enum(ReleaseMode, "mode")
    version_format = _opt_enum(VersionFormat, "version_format")
    version_source = _opt_enum(VersionSource, "version_source")
    default_version = release.get("default_version")
    remotes = release.get("remotes", [])
    tag_template = release.get("tag_template")
    manifest_path = release.get("manifest_path")

    # plugins section
    plugins_data = data.get("plugins", {})
    plugin_config = PluginConfig(
        enable_environment=plugins_data.get("enable_environment", True),
        enable_builtin=plugins_data.get("enable_builtin", True),
        allow_override=plugins_data.get("allow_override", True),
        paths=plugins_data.get("paths", []),
        directories=plugins_data.get("directories", []),
    )

    # monorepo section
    monorepo_data = data.get("monorepo", {})
    packages = []

    for pkg in monorepo_data.get("packages", []):
        packages.append(
            ManagedPackageConfig(
                name=pkg["name"],
                path=pkg["path"],
                language=Language(pkg["language"])
                if "language" in pkg
                else None,
                manifest_path=pkg.get("manifest_path"),
                version_format=VersionFormat(
                    pkg.get("version_format", "major-minor-patch")
                ),
                default_version=pkg.get("default_version", "0.1.0"),
                tag_template=pkg.get("tag_template"),
                version_source=VersionSource(
                    pkg.get("version_source", "manifest")
                ),
            )
        )

    monorepo_config = MonorepoConfig(
        enabled=monorepo_data.get("enabled", False),
        packages=packages,
    )

    return RawConfig(
        language=language,
        mode=mode,
        default_version=default_version,
        version_format=version_format,
        remotes=remotes if isinstance(remotes, list) else [],
        tag_template=tag_template,
        version_source=version_source,
        manifest_path=manifest_path,
        plugins=plugin_config,
        monorepo=monorepo_config,
        source=source,
    )


def load_config_layers(
    repo_root: Path | None = None,
    extra_paths: list[Path] | None = None,
    env: Mapping[str, str] | None = None,
) -> list[RawConfig]:
    """Load all configuration layers in precedence order (lowest first).

    Args:
        repo_root: Optional repository root used for local and embedded
            configuration discovery.
        extra_paths: Additional explicit TOML paths, such as from ``--config``.
        env: Optional environment mapping overriding ``os.environ``.
    """
    from distlift.config.discovery import (
        discover_embedded_pyproject_config,
        discover_local_config_paths,
        discover_system_config_paths,
        discover_user_config_paths,
    )

    layers: list[RawConfig] = []

    # System-wide defaults and user home layers
    for path in discover_system_config_paths():
        data = load_toml_config(path)
        layers.append(_parse_raw_config(data, str(path)))

    for path in discover_user_config_paths():
        data = load_toml_config(path)
        layers.append(_parse_raw_config(data, str(path)))

    if repo_root is not None:
        # Embedded tool table and standalone distlift.toml-style files
        pyproject = discover_embedded_pyproject_config(repo_root)

        if pyproject:
            data = load_pyproject_tool_config(pyproject)
            layers.append(
                _parse_raw_config(data, str(pyproject) + "[tool.distlift]")
            )

        for path in discover_local_config_paths(repo_root):
            data = load_toml_config(path)
            layers.append(_parse_raw_config(data, str(path)))

    # Explicit CLI paths override files discovered from the repository root
    for path in extra_paths or []:
        data = load_toml_config(path)
        layers.append(_parse_raw_config(data, str(path)))

    # Environment variables override all file-based layers when present
    env_data = load_environment_config(env)

    if env_data:
        layers.append(_parse_raw_config(env_data, "environment"))

    return layers
