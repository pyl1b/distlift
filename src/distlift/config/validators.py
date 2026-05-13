from __future__ import annotations

import re

from distlift.config.models import (
    BumpKind,
    HookSpec,
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
    validate_changelog_config(config)
    validate_deploy_config(config)
    validate_hooks_config(config)

    if config.mode == ReleaseMode.MONOREPO:
        validate_monorepo_config(config)

    if config.manifest_path is not None and not config.manifest_path.exists():
        raise ConfigurationError(
            f"Explicit manifest path does not exist: {config.manifest_path}"
        )


_KEEP_A_CHANGELOG_SECTION_TITLES = frozenset(
    {"Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"}
)

_MAX_HOOKS_PER_EVENT = 64


def _validate_hook_spec(spec: HookSpec, *, ctx: str) -> None:
    """Ensure ``spec`` has exactly one of ``shell`` or ``argv``.

    Args:
        spec: Hook entry to validate.
        ctx: Description of the config location for error messages.
    """
    has_shell = spec.shell is not None and str(spec.shell).strip() != ""
    has_argv = spec.argv is not None

    if has_shell and has_argv:
        raise ConfigurationError(f"{ctx}: hook cannot set both shell and argv")

    if not has_shell and not has_argv:
        raise ConfigurationError(f"{ctx}: hook must set either shell or argv")

    if has_argv:
        assert spec.argv is not None
        if not spec.argv:
            raise ConfigurationError(f"{ctx}: hook argv cannot be empty")

        for i, arg in enumerate(spec.argv):
            if not str(arg).strip():
                raise ConfigurationError(
                    f"{ctx}: hook argv entry {i} cannot be empty"
                )


def validate_hooks_config(config: ResolvedConfig) -> None:
    """Validate hook command lists on the resolved configuration.

    Args:
        config: Fully merged configuration including ``hooks``.
    """
    h = config.hooks

    for field_name in (
        "tag_pushed",
        "tag_push_failed",
        "release_failed",
        "build_succeeded",
        "build_failed",
        "publish_succeeded",
        "publish_failed",
    ):
        specs = getattr(h, field_name)

        if len(specs) > _MAX_HOOKS_PER_EVENT:
            raise ConfigurationError(
                f"hooks.{field_name} cannot list more than "
                f"{_MAX_HOOKS_PER_EVENT} commands"
            )

        for i, spec in enumerate(specs):
            _validate_hook_spec(spec, ctx=f"hooks.{field_name}[{i}]")


def validate_changelog_config(config: ResolvedConfig) -> None:
    """Validate changelog-related settings on the resolved configuration.

    Args:
        config: Fully merged configuration including ``changelog``.
    """
    ch = config.changelog
    tpl = ch.compare_url_template.strip()

    if tpl:
        if "{prev}" not in tpl or "{next}" not in tpl:
            raise ConfigurationError(
                "changelog.compare_url_template must contain "
                "both {prev} and {next} placeholders when set"
            )

    if ch.default_section not in _KEEP_A_CHANGELOG_SECTION_TITLES:
        raise ConfigurationError(
            "changelog.default_section must be one of: "
            + ", ".join(sorted(_KEEP_A_CHANGELOG_SECTION_TITLES))
        )

    for ctype, section in ch.commit_mapping.items():
        if section not in _KEEP_A_CHANGELOG_SECTION_TITLES:
            raise ConfigurationError(
                "changelog.commit_mapping values must be Keep a Changelog "
                f"section titles (got {section!r} for type {ctype!r})"
            )


def validate_deploy_config(config: ResolvedConfig) -> None:
    """Validate ``[deploy]`` settings on the resolved configuration.

    Args:
        config: Fully merged configuration including ``deploy``.
    """
    prefix = config.deploy.tag_prefix.strip()

    if not prefix:
        raise ConfigurationError("deploy.tag_prefix cannot be empty")

    if not re.match(r"^[A-Za-z0-9_-]+$", prefix):
        raise ConfigurationError(
            "deploy.tag_prefix must contain only ASCII letters, digits, "
            "underscore, or hyphen"
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
