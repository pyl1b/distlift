from __future__ import annotations

from typing import Sequence, TypeVar

import attrs

from distlift.config.models import (
    ManagedPackageConfig,
    MonorepoConfig,
    PluginConfig,
    RawConfig,
    ResolvedConfig,
    VersionFormat,
    VersionSource,
)
from distlift.constants import DEFAULT_REMOTE, DEFAULT_TAG_TEMPLATE, DEFAULT_VERSION

T = TypeVar("T")


def merge_optional_scalar(
    layers: Sequence[RawConfig],
    attr: str,
    default: T,
    field_sources: dict[str, str],
) -> T:
    value = default
    for layer in layers:
        candidate = getattr(layer, attr, None)
        if candidate is not None:
            value = candidate
            field_sources[attr] = layer.source
    return value  # type: ignore[return-value]


def merge_string_list(
    layers: Sequence[RawConfig],
    attr: str,
    default: list[str],
    field_sources: dict[str, str],
) -> list[str]:
    value = default
    for layer in layers:
        candidate = getattr(layer, attr, None)
        if candidate:
            value = candidate
            field_sources[attr] = layer.source
    return value


def merge_package_maps(
    layers: Sequence[RawConfig],
) -> dict[str, ManagedPackageConfig]:
    result: dict[str, ManagedPackageConfig] = {}
    for layer in layers:
        for pkg in layer.monorepo.packages:
            result[pkg.name] = pkg
    return result


def merge_config_layers(layers: Sequence[RawConfig]) -> ResolvedConfig:
    """Merge ordered config layers into a single ResolvedConfig.

    Each layer overrides the previous for scalar fields; lists are replaced
    entirely by the highest-precedence layer that provides them.
    """
    field_sources: dict[str, str] = {}

    language = merge_optional_scalar(layers, "language", None, field_sources)
    mode = merge_optional_scalar(layers, "mode", None, field_sources)
    default_version = merge_optional_scalar(
        layers, "default_version", DEFAULT_VERSION, field_sources
    )
    version_format = merge_optional_scalar(
        layers, "version_format", VersionFormat.MAJOR_MINOR_PATCH, field_sources
    )
    remotes = merge_string_list(layers, "remotes", [DEFAULT_REMOTE], field_sources)
    tag_template = merge_optional_scalar(
        layers, "tag_template", DEFAULT_TAG_TEMPLATE, field_sources
    )
    version_source = merge_optional_scalar(
        layers, "version_source", VersionSource.MANIFEST, field_sources
    )
    manifest_path_str = merge_optional_scalar(
        layers, "manifest_path", None, field_sources
    )

    # Merge plugin config: last non-default wins per field
    plugin_config = PluginConfig()
    for layer in layers:
        pc = layer.plugins
        plugin_config = attrs.evolve(
            plugin_config,
            enable_environment=pc.enable_environment,
            enable_builtin=pc.enable_builtin,
            allow_override=pc.allow_override,
            paths=pc.paths if pc.paths else plugin_config.paths,
            directories=pc.directories if pc.directories else plugin_config.directories,
        )

    # Merge monorepo config
    packages_map = merge_package_maps(layers)
    monorepo_enabled = False
    for layer in layers:
        if layer.monorepo.enabled:
            monorepo_enabled = True
    monorepo_config = MonorepoConfig(
        enabled=monorepo_enabled,
        packages=list(packages_map.values()),
    )

    from distlift.config.models import ReleaseMode
    from pathlib import Path

    return ResolvedConfig(
        language=language,
        mode=mode or ReleaseMode.SIMPLE,
        default_version=default_version,
        version_format=version_format,
        remotes=remotes,
        tag_template=tag_template,
        version_source=version_source,
        manifest_path=Path(manifest_path_str) if manifest_path_str else None,
        plugins=plugin_config,
        monorepo=monorepo_config,
        field_sources=field_sources,
    )
