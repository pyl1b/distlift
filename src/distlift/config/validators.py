from __future__ import annotations

import re

from distlift.config.models import (
    BumpKind,
    ReleaseMode,
    ResolvedConfig,
    VersionFormat,
)
from distlift.errors import ConfigurationError, VersionError
from distlift.versioning.bump import validate_bump_allowed


def validate_resolved_config(config: ResolvedConfig) -> None:
    """Validate a merged configuration before planning or executing releases.

    Args:
        config: Fully merged repository configuration to validate.
    """
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
    """Ensure the configured version format is a known enum member.

    Args:
        config: Merged configuration whose ``version_format`` is checked.
    """
    fmt = config.version_format

    if fmt not in VersionFormat:
        raise ConfigurationError(f"Unsupported version format: {fmt!r}")


def validate_monorepo_config(config: ResolvedConfig) -> None:
    """Validate monorepo-specific fields when monorepo mode is enabled.

    Args:
        config: Merged configuration including the ``monorepo`` section.
    """
    if not config.monorepo.packages:
        raise ConfigurationError(
            "Monorepo mode requires at least one package declared in "
            "[monorepo.packages]"
        )

    names = [p.name for p in config.monorepo.packages]

    if len(names) != len(set(names)):
        raise ConfigurationError(
            "Duplicate package names in monorepo configuration"
        )

    for pkg in config.monorepo.packages:
        if not pkg.path:
            raise ConfigurationError(
                f"Package '{pkg.name}' is missing a 'path' declaration"
            )


def validate_remote_names(config: ResolvedConfig) -> None:
    """Ensure each configured Git remote name is syntactically safe.

    Args:
        config: Merged configuration whose ``remotes`` list is checked.
    """
    for remote in config.remotes:
        if not remote or not re.match(r"^[\w.\-]+$", remote):
            raise ConfigurationError(f"Invalid remote name: {remote!r}")


def validate_tag_template(config: ResolvedConfig) -> None:
    """Ensure the tag template contains the ``{version}`` placeholder.

    Args:
        config: Merged configuration whose ``tag_template`` is checked.
    """
    if "{version}" not in config.tag_template:
        raise ConfigurationError(
            f"Tag template '{config.tag_template}' must contain {{version}}"
        )


def validate_bump_for_config(config: ResolvedConfig, bump: BumpKind) -> None:
    """Validate that a bump kind is allowed for the configured version format.

    Args:
        config: Merged configuration providing ``version_format``.
        bump: Requested bump kind for the next release version.
    """
    try:
        validate_bump_allowed(config.version_format, bump)
    except VersionError as exc:
        raise ConfigurationError(str(exc)) from exc
