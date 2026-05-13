from __future__ import annotations

import re

from distlift.config.models import (
    BumpKind,
    Language,
    ReleaseMode,
    ResolvedConfig,
    VersionFormat,
)
from distlift.errors import ConfigurationError
from distlift.versioning.bump import validate_bump_allowed


def validate_resolved_config(config: ResolvedConfig) -> None:
    validate_version_policy(config)
    validate_remote_names(config)
    validate_tag_template(config)
    if config.mode == ReleaseMode.MONOREPO:
        validate_monorepo_config(config)
    if config.manifest_path is not None and not config.manifest_path.exists():
        raise ConfigurationError(
            f"Explicit manifest path does not exist: {config.manifest_path}"
        )


def validate_version_policy(config: ResolvedConfig) -> None:
    fmt = config.version_format
    if fmt not in VersionFormat:
        raise ConfigurationError(f"Unsupported version format: {fmt!r}")


def validate_monorepo_config(config: ResolvedConfig) -> None:
    if not config.monorepo.packages:
        raise ConfigurationError(
            "Monorepo mode requires at least one package declared in [monorepo.packages]"
        )
    names = [p.name for p in config.monorepo.packages]
    if len(names) != len(set(names)):
        raise ConfigurationError("Duplicate package names in monorepo configuration")
    for pkg in config.monorepo.packages:
        if not pkg.path:
            raise ConfigurationError(
                f"Package '{pkg.name}' is missing a 'path' declaration"
            )


def validate_remote_names(config: ResolvedConfig) -> None:
    for remote in config.remotes:
        if not remote or not re.match(r"^[\w.\-]+$", remote):
            raise ConfigurationError(f"Invalid remote name: {remote!r}")


def validate_tag_template(config: ResolvedConfig) -> None:
    if "{version}" not in config.tag_template:
        raise ConfigurationError(
            f"Tag template '{config.tag_template}' must contain {{version}}"
        )


def validate_bump_for_config(config: ResolvedConfig, bump: BumpKind) -> None:
    try:
        validate_bump_allowed(config.version_format, bump)
    except Exception as exc:
        raise ConfigurationError(str(exc)) from exc
