"""Load raw configuration fragments from TOML files and environment."""

from __future__ import annotations

import json
import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from distlift.config.models import (
    BuildConfig,
    BuildTargetConfig,
    DependencyUpdateRule,
    DependencyUpdatesConfig,
    DependencyUpgradesConfig,
    ExternalMonorepoDependencyUpdateConfig,
    HooksConfig,
    HookSpec,
    Language,
    ManagedPackageConfig,
    MonorepoConfig,
    PluginConfig,
    PublishConfig,
    PublishTargetConfig,
    RawConfig,
    ReleaseMode,
    VersionFileConfig,
    VersionFormat,
    VersionSource,
)
from distlift.constants import (
    ENV_PREFIX,
    HOOK_ENV_KEY_SUFFIXES,
    PYPROJECT_TOOL_KEY,
)
from distlift.errors import ConfigurationError

_CHANGELOG_ALLOWED_KEYS = frozenset(
    {
        "enabled",
        "path",
        "title",
        "header_text",
        "date_format",
        "include_unreleased_section",
        "compare_url_template",
        "skip_commit_types",
        "commit_mapping",
        "default_section",
        "prompt_editor",
    }
)

_DEPLOY_ALLOWED_KEYS = frozenset({"tag_prefix", "verify_indexes"})


def _deploy_overlay_from_mapping(mapping: Any) -> dict[str, Any]:
    """Return only recognized deploy keys from a parsed mapping.

    Args:
        mapping: Value read from a ``deploy`` table or similar structure.
    """
    if not isinstance(mapping, dict):
        return {}

    return {
        str(k): v for k, v in mapping.items() if str(k) in _DEPLOY_ALLOWED_KEYS
    }


def _dependency_update_rule_from_mapping(item: Any) -> DependencyUpdateRule:
    """Parse one ``[[dependency_updates.rules]]`` table entry.

    Args:
        item: Mapping with rule fields from TOML.
    """
    if not isinstance(item, Mapping):
        raise ConfigurationError(
            "Each dependency_updates.rules entry must be a table"
        )

    package_raw = item.get("package")

    if not isinstance(package_raw, str) or not package_raw.strip():
        raise ConfigurationError(
            "dependency_updates.rules entry requires non-empty 'package'"
        )

    dep_name = item.get("dependency_name")
    projects_raw = item.get("projects", ["*"])
    projects: list[str] = []

    if isinstance(projects_raw, list):
        projects = [str(p).strip() for p in projects_raw if str(p).strip()]

    if not projects:
        projects = ["*"]

    version_template = item.get("version_template")

    return DependencyUpdateRule(
        package=package_raw.strip(),
        dependency_name=(
            str(dep_name).strip() if isinstance(dep_name, str) else None
        ),
        projects=projects,
        version_template=(
            str(version_template).strip()
            if isinstance(version_template, str)
            else None
        ),
    )


def _external_monorepo_from_mapping(
    item: Any,
) -> ExternalMonorepoDependencyUpdateConfig:
    """Parse one ``[[dependency_updates.external_monorepos]]`` table entry.

    Args:
        item: Mapping with external monorepo fields from TOML.
    """
    if not isinstance(item, Mapping):
        raise ConfigurationError(
            "Each dependency_updates.external_monorepos entry must be a table"
        )

    path_raw = item.get("path")

    if not isinstance(path_raw, str) or not path_raw.strip():
        raise ConfigurationError(
            "dependency_updates.external_monorepos entry requires "
            "non-empty 'path'"
        )

    config_paths_raw = item.get("config_paths", [])
    config_paths: list[str] = []

    if isinstance(config_paths_raw, list):
        config_paths = [
            str(p).strip() for p in config_paths_raw if str(p).strip()
        ]

    projects_raw = item.get("projects", ["*"])
    projects: list[str] = []

    if isinstance(projects_raw, list):
        projects = [str(p).strip() for p in projects_raw if str(p).strip()]

    if not projects:
        projects = ["*"]

    return ExternalMonorepoDependencyUpdateConfig(
        path=path_raw.strip(),
        config_paths=config_paths,
        projects=projects,
    )


def dependency_updates_from_mapping(
    mapping: Any,
) -> DependencyUpdatesConfig:
    """Build ``DependencyUpdatesConfig`` from a ``[dependency_updates]`` table.

    Args:
        mapping: Parsed mapping for the dependency_updates section.
    """
    if not isinstance(mapping, dict):
        return DependencyUpdatesConfig()

    rules: list[DependencyUpdateRule] = []
    rules_raw = mapping.get("rules", [])

    if isinstance(rules_raw, list):
        for item in rules_raw:
            rules.append(_dependency_update_rule_from_mapping(item))

    external: list[ExternalMonorepoDependencyUpdateConfig] = []
    ext_raw = mapping.get("external_monorepos", [])

    if isinstance(ext_raw, list):
        for item in ext_raw:
            external.append(_external_monorepo_from_mapping(item))

    kw: dict[str, Any] = {}

    if "enabled" in mapping:
        kw["enabled"] = bool(mapping["enabled"])

    if "include_current_monorepo" in mapping:
        kw["include_current_monorepo"] = bool(
            mapping["include_current_monorepo"]
        )

    if "python_version_template" in mapping:
        kw["python_version_template"] = str(mapping["python_version_template"])

    if "javascript_version_template" in mapping:
        kw["javascript_version_template"] = str(
            mapping["javascript_version_template"]
        )

    return DependencyUpdatesConfig(
        rules=rules,
        external_monorepos=external,
        **kw,
    )


def dependency_upgrades_from_mapping(
    mapping: Any,
) -> DependencyUpgradesConfig:
    """Build ``DependencyUpgradesConfig`` from a ``[dependency_upgrades]`` table.

    Args:
        mapping: Parsed mapping for the dependency_upgrades section.
    """
    if not isinstance(mapping, dict):
        return DependencyUpgradesConfig()

    kw: dict[str, Any] = {}

    if "enabled" in mapping:
        kw["enabled"] = bool(mapping["enabled"])

    if "registry_timeout_seconds" in mapping:
        kw["registry_timeout_seconds"] = int(
            mapping["registry_timeout_seconds"]
        )

    if "lock_refresh_timeout_seconds" in mapping:
        kw["lock_refresh_timeout_seconds"] = int(
            mapping["lock_refresh_timeout_seconds"]
        )

    if "registry_max_workers" in mapping:
        kw["registry_max_workers"] = int(mapping["registry_max_workers"])

    if "respect_receive_enabled" in mapping:
        kw["respect_receive_enabled"] = bool(
            mapping["respect_receive_enabled"]
        )

    if "install_packages" in mapping:
        kw["install_packages"] = bool(mapping["install_packages"])

    if "install_timeout_seconds" in mapping:
        kw["install_timeout_seconds"] = int(mapping["install_timeout_seconds"])

    package_managers: dict[str, str] = {}
    pm_raw = mapping.get("package_managers")

    if isinstance(pm_raw, dict):
        for key, value in pm_raw.items():
            if str(key).strip() and str(value).strip():
                package_managers[str(key).strip()] = str(value).strip()

    return DependencyUpgradesConfig(package_managers=package_managers, **kw)


def _changelog_overlay_from_mapping(mapping: Any) -> dict[str, Any]:
    """Return only recognized changelog keys from a parsed mapping.

    Args:
        mapping: Value read from a ``changelog`` table or similar structure.
    """
    if not isinstance(mapping, dict):
        return {}

    return {
        str(k): v
        for k, v in mapping.items()
        if str(k) in _CHANGELOG_ALLOWED_KEYS
    }


_HOOK_LIST_FIELDS = frozenset(
    {
        "tag_pushed",
        "tag_push_failed",
        "release_failed",
        "build_succeeded",
        "build_failed",
        "publish_succeeded",
        "publish_failed",
        "dependencies_autoupdated",
    }
)


def _hook_spec_from_toml_item(item: Any) -> HookSpec:
    """Convert one TOML hook table entry or string into a ``HookSpec``.

    Args:
        item: A string (shell command) or a mapping with ``shell`` or
            ``argv``.
    """
    if isinstance(item, str):
        return HookSpec(shell=item)

    if isinstance(item, dict):
        shell = item.get("shell")
        argv = item.get("argv")

        if shell is not None and argv is not None:
            msg = "Hook entry cannot set both 'shell' and 'argv'"
            raise ValueError(msg)

        if shell is not None:
            return HookSpec(shell=str(shell))

        if argv is not None:
            if not isinstance(argv, list):
                msg = "Hook 'argv' must be a list of strings"
                raise ValueError(msg)
            return HookSpec(argv=[str(x) for x in argv])

    msg = "Hook entry must be a string or table with 'shell' or 'argv'"
    raise ValueError(msg)


def _hook_specs_from_toml_list(raw: Any) -> list[HookSpec]:
    """Parse a TOML list of hook entries into ``HookSpec`` objects.

    Args:
        raw: Sequence of hook entry values under an event key.
    """
    if not isinstance(raw, list):
        return []

    return [_hook_spec_from_toml_item(x) for x in raw]


def hooks_config_from_mapping(mapping: Any) -> HooksConfig:
    """Build a ``HooksConfig`` from a parsed ``[hooks]`` table or similar.

    Args:
        mapping: Parsed mapping whose keys are hook event names.
    """
    if not isinstance(mapping, dict):
        return HooksConfig()

    kw: dict[str, list[HookSpec]] = {}

    for key in _HOOK_LIST_FIELDS:
        if key not in mapping:
            continue
        kw[key] = _hook_specs_from_toml_list(mapping[key])

    return HooksConfig(**kw)


def parse_hooks_env_value(value: str) -> list[HookSpec]:
    """Parse ``DISTLIFT_HOOKS_*`` text into hook specs.

    When the trimmed value starts with ``[``, it is parsed as JSON: an array
    of strings (shell hooks) or arrays of strings (``argv`` hooks). Otherwise
    the value is split on newlines; each non-empty line is one shell hook.

    Args:
        value: Raw environment variable text.
    """
    trimmed = value.strip()

    if not trimmed:
        return []

    if trimmed.startswith("["):
        data = json.loads(trimmed)

        if not isinstance(data, list):
            msg = "DISTLIFT_HOOKS JSON must be a top-level array"
            raise ValueError(msg)

        specs: list[HookSpec] = []

        for entry in data:
            if isinstance(entry, str):
                specs.append(HookSpec(shell=entry))
                continue

            if isinstance(entry, list):
                specs.append(HookSpec(argv=[str(x) for x in entry]))
                continue

            msg = "Each DISTLIFT_HOOKS JSON entry must be a string or array"
            raise ValueError(msg)

        return specs

    lines = [ln.strip() for ln in value.splitlines() if ln.strip()]

    return [HookSpec(shell=ln) for ln in lines]


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

    if v := _get("EDITOR"):
        stripped = v.strip()
        if stripped:
            result["editor"] = stripped

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

    changelog_env: dict[str, Any] = {}

    if v := _get("CHANGELOG_ENABLED"):
        changelog_env["enabled"] = v.lower() in ("1", "true", "yes")

    if v := _get("CHANGELOG_PATH"):
        changelog_env["path"] = v

    if v := _get("CHANGELOG_COMPARE_URL_TEMPLATE"):
        changelog_env["compare_url_template"] = v

    if v := _get("CHANGELOG_TITLE"):
        changelog_env["title"] = v

    if v := _get("CHANGELOG_PROMPT_EDITOR"):
        changelog_env["prompt_editor"] = v.lower() in ("1", "true", "yes")

    if changelog_env:
        result["changelog"] = changelog_env

    deploy_env: dict[str, Any] = {}

    if v := _get("DEPLOY_TAG_PREFIX"):
        stripped = str(v).strip()

        if stripped:
            deploy_env["tag_prefix"] = stripped

    if v := _get("DEPLOY_VERIFY_INDEXES"):
        deploy_env["verify_indexes"] = v.lower() in ("1", "true", "yes")

    if deploy_env:
        result["deploy"] = deploy_env

    dep_env: dict[str, Any] = {}

    if v := _get("DEPENDENCY_UPDATES_ENABLED"):
        dep_env["enabled"] = v.lower() in ("1", "true", "yes")

    if v := _get("DEPENDENCY_UPDATES_INCLUDE_CURRENT_MONOREPO"):
        dep_env["include_current_monorepo"] = v.lower() in (
            "1",
            "true",
            "yes",
        )

    if dep_env:
        result["dependency_updates"] = dep_env

    upgrades_env: dict[str, Any] = {}

    if v := _get("DEPENDENCY_UPGRADES_ENABLED"):
        upgrades_env["enabled"] = v.lower() in ("1", "true", "yes")

    if v := _get("DEPENDENCY_UPGRADES_INSTALL_PACKAGES"):
        upgrades_env["install_packages"] = v.lower() in ("1", "true", "yes")

    if upgrades_env:
        result["dependency_upgrades"] = upgrades_env

    hooks_append_kw: dict[str, list[HookSpec]] = {}

    for event_key, suffix in HOOK_ENV_KEY_SUFFIXES.items():
        raw_hook_env = env.get(f"{ENV_PREFIX}HOOKS_{suffix}")

        if raw_hook_env is None or not str(raw_hook_env).strip():
            continue

        try:
            hooks_append_kw[event_key] = parse_hooks_env_value(
                str(raw_hook_env)
            )
        except (json.JSONDecodeError, ValueError) as exc:
            raise ConfigurationError(
                f"Invalid {ENV_PREFIX}HOOKS_{suffix} value: {exc}"
            ) from exc

    if hooks_append_kw:
        result["hooks_append"] = HooksConfig(
            **{fn: hooks_append_kw.get(fn, []) for fn in _HOOK_LIST_FIELDS}
        )

    return result


def _version_file_from_mapping(item: Any, source: str) -> VersionFileConfig:
    """Parse one ``[[version_files]]`` table entry.

    Args:
        item: Mapping with version file fields from TOML.
        source: Config layer label included in error messages.
    """
    if not isinstance(item, Mapping):
        raise ConfigurationError(
            f"Each version_files entry must be a table ({source})"
        )

    path_raw = item.get("path")
    kind_raw = item.get("kind")
    lang_raw = item.get("language")
    primary = item.get("primary", False)
    update = item.get("update", True)

    language: Language | None = None
    if lang_raw is not None:
        try:
            language = Language(str(lang_raw))
        except ValueError:
            raise ConfigurationError(
                f"version_files entry has unknown language {lang_raw!r}"
                f" ({source})"
            )

    return VersionFileConfig(
        path=str(path_raw).strip() if isinstance(path_raw, str) else None,
        kind=str(kind_raw).strip() if isinstance(kind_raw, str) else None,
        language=language,
        primary=bool(primary),
        update=bool(update),
    )


def _version_files_from_list(raw: Any, source: str) -> list[VersionFileConfig]:
    """Parse a list of version file table entries.

    Args:
        raw: Sequence of version file mappings from TOML.
        source: Config layer label included in error messages.
    """
    if not isinstance(raw, list):
        return []
    return [_version_file_from_mapping(item, source) for item in raw]


def _managed_package_from_monorepo_item(
    item: Any, source: str
) -> ManagedPackageConfig:
    """Normalize one ``monorepo.packages`` entry into a managed package.

    Args:
        item: Either a repo-relative path string (name derived from the last
            path segment) or a mapping with ``name`` and ``path`` keys.
        source: Config layer label included in error messages.
    """
    # Shorthand: a string is the repo-relative package root; ``name`` is the
    # final path segment.
    if isinstance(item, str):
        path = item.strip()

        if not path:
            raise ConfigurationError(
                "Monorepo package path cannot be empty "
                f"(check [monorepo].packages in {source})"
            )

        name = Path(path).name

        if not name or name in {".", ".."}:
            raise ConfigurationError(
                f"Cannot derive monorepo package name from path "
                f"{path!r} ({source})"
            )

        return ManagedPackageConfig(
            name=name,
            path=path,
        )

    # Explicit table row: ``name`` and ``path`` plus optional per-package keys.
    if isinstance(item, Mapping):
        name_raw = item.get("name")
        path_raw = item.get("path")

        if not isinstance(name_raw, str) or not name_raw.strip():
            raise ConfigurationError(
                "Monorepo package entry requires a non-empty string"
                f" 'name' ({source})"
            )

        if not isinstance(path_raw, str) or not path_raw.strip():
            label = name_raw.strip()
            raise ConfigurationError(
                f"Monorepo package entry {label!r} requires a"
                f" non-empty string 'path' ({source})"
            )

        pkg = item
        trigger_enabled = pkg.get("dependency_updates_trigger_enabled", True)
        receive_enabled = pkg.get("dependency_updates_receive_enabled", True)

        if not isinstance(trigger_enabled, bool):
            raise ConfigurationError(
                f"Package {name_raw.strip()!r}: "
                "dependency_updates_trigger_enabled must be a boolean "
                f"({source})"
            )

        if not isinstance(receive_enabled, bool):
            raise ConfigurationError(
                f"Package {name_raw.strip()!r}: "
                "dependency_updates_receive_enabled must be a boolean "
                f"({source})"
            )

        version_files = _version_files_from_list(
            pkg.get("version_files", []), source
        )

        change_paths_raw = pkg.get("change_paths", [])
        change_paths: list[str] = []
        if isinstance(change_paths_raw, list):
            change_paths = [
                str(p).strip() for p in change_paths_raw if str(p).strip()
            ]

        return ManagedPackageConfig(
            name=name_raw.strip(),
            path=path_raw.strip(),
            language=Language(pkg["language"]) if "language" in pkg else None,
            manifest_path=pkg.get("manifest_path"),
            version_format=VersionFormat(
                pkg.get("version_format", "major-minor-patch")
            ),
            default_version=pkg.get("default_version", "0.1.0"),
            tag_template=pkg.get("tag_template"),
            version_source=VersionSource(
                pkg.get("version_source", "manifest")
            ),
            changelog_path=pkg.get("changelog_path"),
            dependency_updates_trigger_enabled=trigger_enabled,
            dependency_updates_receive_enabled=receive_enabled,
            version_files=version_files,
            change_paths=change_paths,
        )

    raise ConfigurationError(
        f"Each monorepo.packages entry must be a path string or a table; "
        f"got {type(item).__name__} ({source})"
    )


def _build_target_from_mapping(item: Any, source: str) -> BuildTargetConfig:
    """Parse one ``[[build.targets]]`` table entry.

    Args:
        item: Mapping with build target fields from TOML.
        source: Config layer label included in error messages.
    """
    if not isinstance(item, Mapping):
        raise ConfigurationError(
            f"Each build.targets entry must be a table ({source})"
        )

    name_raw = item.get("name")
    if not isinstance(name_raw, str) or not name_raw.strip():
        raise ConfigurationError(
            f"build.targets entry requires non-empty 'name' ({source})"
        )

    artifacts_raw = item.get("artifacts", [])
    artifacts: list[str] = []
    if isinstance(artifacts_raw, list):
        artifacts = [str(a) for a in artifacts_raw]

    return BuildTargetConfig(
        name=name_raw.strip(),
        path=str(item.get("path", ".")).strip() or ".",
        ecosystem=str(item.get("ecosystem", "python")).strip(),
        command=str(item["command"]).strip()
        if isinstance(item.get("command"), str)
        else None,
        artifacts=artifacts,
    )


def _build_config_from_mapping(mapping: Any, source: str) -> BuildConfig:
    """Build a ``BuildConfig`` from a parsed ``[build]`` section.

    Args:
        mapping: Parsed mapping for the build section.
        source: Config layer label included in error messages.
    """
    if not isinstance(mapping, dict):
        return BuildConfig()

    targets: list[BuildTargetConfig] = []
    for item in mapping.get("targets", []):
        targets.append(_build_target_from_mapping(item, source))

    return BuildConfig(targets=targets)


def _publish_target_from_mapping(
    item: Any, source: str
) -> PublishTargetConfig:
    """Parse one ``[[publish.targets]]`` table entry.

    Args:
        item: Mapping with publish target fields from TOML.
        source: Config layer label included in error messages.
    """
    if not isinstance(item, Mapping):
        raise ConfigurationError(
            f"Each publish.targets entry must be a table ({source})"
        )

    name_raw = item.get("name")
    if not isinstance(name_raw, str) or not name_raw.strip():
        raise ConfigurationError(
            f"publish.targets entry requires non-empty 'name' ({source})"
        )

    return PublishTargetConfig(
        name=name_raw.strip(),
        path=str(item.get("path", ".")).strip() or ".",
        ecosystem=str(item.get("ecosystem", "python")).strip(),
    )


def _publish_config_from_mapping(mapping: Any, source: str) -> PublishConfig:
    """Build a ``PublishConfig`` from a parsed ``[publish]`` section.

    Args:
        mapping: Parsed mapping for the publish section.
        source: Config layer label included in error messages.
    """
    if not isinstance(mapping, dict):
        return PublishConfig()

    targets: list[PublishTargetConfig] = []
    for item in mapping.get("targets", []):
        targets.append(_publish_target_from_mapping(item, source))

    return PublishConfig(targets=targets)


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

    # Top-level version_files (simple mode)
    version_files = _version_files_from_list(
        data.get("version_files", []), source
    )

    # Optional editor fallback used when GIT_EDITOR/VISUAL/EDITOR are unset
    raw_editor = release.get("editor")
    if isinstance(raw_editor, str):
        stripped_editor = raw_editor.strip()
        editor = stripped_editor if stripped_editor else None
    else:
        editor = None

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
        packages.append(_managed_package_from_monorepo_item(pkg, source))

    monorepo_config = MonorepoConfig(
        enabled=monorepo_data.get("enabled", False),
        packages=packages,
    )

    changelog_overlay = _changelog_overlay_from_mapping(data.get("changelog"))

    deploy_overlay = _deploy_overlay_from_mapping(data.get("deploy"))

    dependency_updates = dependency_updates_from_mapping(
        data.get("dependency_updates")
    )

    dependency_upgrades = dependency_upgrades_from_mapping(
        data.get("dependency_upgrades")
    )

    hooks = hooks_config_from_mapping(data.get("hooks", {}))

    hooks_append_raw = data.get("hooks_append")
    if isinstance(hooks_append_raw, HooksConfig):
        hooks_append = hooks_append_raw
    else:
        hooks_append = hooks_config_from_mapping(hooks_append_raw or {})

    build_config = _build_config_from_mapping(data.get("build", {}), source)
    publish_config = _publish_config_from_mapping(
        data.get("publish", {}), source
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
        version_files=version_files,
        editor=editor,
        plugins=plugin_config,
        monorepo=monorepo_config,
        changelog_overlay=changelog_overlay,
        deploy_overlay=deploy_overlay,
        dependency_updates=dependency_updates,
        dependency_upgrades=dependency_upgrades,
        hooks=hooks,
        hooks_append=hooks_append,
        build=build_config,
        publish=publish_config,
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
