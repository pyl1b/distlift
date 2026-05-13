from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, TypeVar

import attrs

from distlift.config.models import (
    ChangelogConfig,
    HooksConfig,
    ManagedPackageConfig,
    MonorepoConfig,
    PluginConfig,
    RawConfig,
    ReleaseMode,
    ResolvedConfig,
    VersionFormat,
    VersionSource,
)
from distlift.constants import (
    DEFAULT_REMOTE,
    DEFAULT_TAG_TEMPLATE,
    DEFAULT_VERSION,
)

T = TypeVar("T")


def changelog_from_merged_overlay(overlay: dict[str, Any]) -> ChangelogConfig:
    """Build a ``ChangelogConfig`` from merged overlay key-values.

    Args:
        overlay: Merged mapping of changelog keys from configuration layers.
    """
    base = ChangelogConfig()

    if not overlay:
        return base

    kw: dict[str, Any] = {}

    if "enabled" in overlay:
        kw["enabled"] = bool(overlay["enabled"])

    if "path" in overlay:
        kw["path"] = str(overlay["path"])

    if "title" in overlay:
        kw["title"] = str(overlay["title"])

    if "header_text" in overlay:
        kw["header_text"] = str(overlay["header_text"])

    if "date_format" in overlay:
        kw["date_format"] = str(overlay["date_format"])

    if "include_unreleased_section" in overlay:
        kw["include_unreleased_section"] = bool(
            overlay["include_unreleased_section"]
        )

    if "compare_url_template" in overlay:
        kw["compare_url_template"] = str(overlay["compare_url_template"])

    if "prompt_editor" in overlay:
        kw["prompt_editor"] = bool(overlay["prompt_editor"])

    if "skip_commit_types" in overlay:
        raw_skip = overlay["skip_commit_types"]

        if isinstance(raw_skip, list):
            kw["skip_commit_types"] = [str(x) for x in raw_skip]

    if "commit_mapping" in overlay:
        raw_map = overlay["commit_mapping"]

        if isinstance(raw_map, dict):
            kw["commit_mapping"] = {str(k): str(v) for k, v in raw_map.items()}

    if "default_section" in overlay:
        kw["default_section"] = str(overlay["default_section"])

    return attrs.evolve(base, **kw)


def merge_changelog_overlays(layers: Sequence[RawConfig]) -> ChangelogConfig:
    """Merge changelog overlay fragments from all layers (low to high).

    Args:
        layers: Raw configuration fragments ordered low to high precedence.
    """
    merged: dict[str, Any] = {}

    for layer in layers:
        merged.update(layer.changelog_overlay)

    return changelog_from_merged_overlay(merged)


_HOOK_MERGE_FIELDS = (
    "tag_pushed",
    "tag_push_failed",
    "release_failed",
    "build_succeeded",
    "build_failed",
    "publish_succeeded",
    "publish_failed",
)


def merge_hooks_layers(layers: Sequence[RawConfig]) -> HooksConfig:
    """Merge hook specs: last non-empty TOML layer per event, then append env.

    Args:
        layers: Raw configuration fragments ordered low to high precedence.
    """
    base = HooksConfig()

    # Last non-empty ``hooks`` field per event replaces the list (file layers)
    for layer in layers:
        h = layer.hooks

        for fn in _HOOK_MERGE_FIELDS:
            lst = getattr(h, fn)

            if lst:
                base = attrs.evolve(base, **{fn: list(lst)})

    # Append specs from ``hooks_append`` on each layer in order
    for layer in layers:
        ha = layer.hooks_append

        for fn in _HOOK_MERGE_FIELDS:
            extra = getattr(ha, fn)

            if not extra:
                continue

            cur = list(getattr(base, fn)) + list(extra)
            base = attrs.evolve(base, **{fn: cur})

    return base


def merge_optional_scalar(
    layers: Sequence[RawConfig],
    getter: Callable[[RawConfig], T | None],
    field_name: str,
    default: T,
    field_sources: dict[str, str],
) -> T:
    """Return the last non-``None`` scalar contributed by any layer.

    Args:
        layers: Configuration layers from lowest to highest precedence.
        getter: Reads the candidate scalar value from a single layer.
        field_name: Key recorded in ``field_sources`` when a layer wins.
        default: Value used when no layer supplies a non-``None`` value.
        field_sources: Map updated with the winning source per field name.
    """
    value = default

    for layer in layers:
        candidate = getter(layer)

        if candidate is not None:
            value = candidate
            field_sources[field_name] = layer.source

    return value  # type: ignore[return-value]


def merge_string_list(
    layers: Sequence[RawConfig],
    getter: Callable[[RawConfig], list[str]],
    field_name: str,
    default: list[str],
    field_sources: dict[str, str],
) -> list[str]:
    """Return the last non-empty string list contributed by any layer.

    Args:
        layers: Configuration layers from lowest to highest precedence.
        getter: Reads the candidate list value from a single layer.
        field_name: Key recorded in ``field_sources`` when a layer wins.
        default: Value used when every layer yields an empty list.
        field_sources: Map updated with the winning source per field name.
    """
    value = default

    for layer in layers:
        candidate = getter(layer)

        if candidate:
            value = candidate
            field_sources[field_name] = layer.source

    return value


def merge_package_maps(
    layers: Sequence[RawConfig],
) -> dict[str, ManagedPackageConfig]:
    """Merge monorepo package declarations across layers by package name.

    Args:
        layers: Configuration layers from lowest to highest precedence.
    """
    result: dict[str, ManagedPackageConfig] = {}

    for layer in layers:
        for pkg in layer.monorepo.packages:
            result[pkg.name] = pkg

    return result


def merge_config_layers(layers: Sequence[RawConfig]) -> ResolvedConfig:
    """Merge ordered config layers into a single ``ResolvedConfig``.

    Each layer overrides the previous for scalar fields; remote lists are
    replaced entirely by the highest-precedence layer that provides a
    non-empty list.

    Args:
        layers: Raw configuration fragments ordered low to high precedence.
    """
    field_sources: dict[str, str] = {}

    language = merge_optional_scalar(
        layers,
        lambda layer: layer.language,
        "language",
        None,
        field_sources,
    )
    mode = merge_optional_scalar(
        layers,
        lambda layer: layer.mode,
        "mode",
        None,
        field_sources,
    )
    default_version = merge_optional_scalar(
        layers,
        lambda layer: layer.default_version,
        "default_version",
        DEFAULT_VERSION,
        field_sources,
    )
    version_format = merge_optional_scalar(
        layers,
        lambda layer: layer.version_format,
        "version_format",
        VersionFormat.MAJOR_MINOR_PATCH,
        field_sources,
    )
    remotes = merge_string_list(
        layers,
        lambda layer: layer.remotes,
        "remotes",
        [DEFAULT_REMOTE],
        field_sources,
    )
    tag_template = merge_optional_scalar(
        layers,
        lambda layer: layer.tag_template,
        "tag_template",
        DEFAULT_TAG_TEMPLATE,
        field_sources,
    )
    version_source = merge_optional_scalar(
        layers,
        lambda layer: layer.version_source,
        "version_source",
        VersionSource.MANIFEST,
        field_sources,
    )
    manifest_path_str = merge_optional_scalar(
        layers,
        lambda layer: layer.manifest_path,
        "manifest_path",
        None,
        field_sources,
    )
    editor = merge_optional_scalar(
        layers,
        lambda layer: layer.editor,
        "editor",
        None,
        field_sources,
    )

    # Merge plugin config so later layers override earlier plugin fields
    plugin_config = PluginConfig()

    for layer in layers:
        pc = layer.plugins
        plugin_config = attrs.evolve(
            plugin_config,
            enable_environment=pc.enable_environment,
            enable_builtin=pc.enable_builtin,
            allow_override=pc.allow_override,
            paths=pc.paths if pc.paths else plugin_config.paths,
            directories=pc.directories
            if pc.directories
            else plugin_config.directories,
        )

    # Build monorepo config by OR-ing enabled flags and merging packages
    packages_map = merge_package_maps(layers)
    monorepo_enabled = False

    for layer in layers:
        if layer.monorepo.enabled:
            monorepo_enabled = True

    monorepo_config = MonorepoConfig(
        enabled=monorepo_enabled,
        packages=list(packages_map.values()),
    )

    changelog_config = merge_changelog_overlays(layers)

    hooks_config = merge_hooks_layers(layers)

    return ResolvedConfig(
        language=language,
        mode=mode or ReleaseMode.SIMPLE,
        default_version=default_version,
        version_format=version_format,
        remotes=remotes,
        tag_template=tag_template,
        version_source=version_source,
        manifest_path=Path(manifest_path_str) if manifest_path_str else None,
        editor=editor,
        plugins=plugin_config,
        monorepo=monorepo_config,
        changelog=changelog_config,
        hooks=hooks_config,
        field_sources=field_sources,
    )
