"""Typer-based CLI for distlift (release, config, and plugin commands)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import attrs
import typer

from distlift.app import DistliftApplication
from distlift.cli_changelog import changelog_app
from distlift.config.files import (
    ConfigScope,
    create_config_file,
    open_config_file_in_editor,
)
from distlift.config.models import BumpKind, ResolvedConfig
from distlift.config.validators import validate_resolved_config
from distlift.constants import ENV_PREFIX, HOOK_ENV_KEY_SUFFIXES
from distlift.errors import ConfigurationError
from distlift.logging_utils import configure_logging
from distlift.plugins.base import DistliftPlugin
from distlift.release.models import (
    MonorepoReleaseRequest,
    SimpleReleaseRequest,
)

app = typer.Typer(
    name="distlift",
    help=(
        "Release orchestrator for Python and JavaScript packages. "
        "With no subcommand, bumps patch, updates manifests, commits, tags, "
        "and pushes. Use --build or --publish to add distribution steps."
    ),
)
release_app = typer.Typer(help="Release commands.", no_args_is_help=True)
config_app = typer.Typer(help="Configuration commands.", no_args_is_help=True)
plugins_app = typer.Typer(help="Plugin commands.", no_args_is_help=True)

app.add_typer(release_app, name="release")
app.add_typer(config_app, name="config")
app.add_typer(plugins_app, name="plugins")
app.add_typer(changelog_app, name="changelog")


@app.callback(invoke_without_command=True)
def distlift_main_callback(
    ctx: typer.Context,
    config_path: Annotated[
        Path | None,
        typer.Option("--config", help="Extra config file"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help=(
                "Plan-only release (no Git writes); if combined with "
                "--publish, skip registry upload but may still build."
            ),
        ),
    ] = False,
    build: Annotated[
        bool,
        typer.Option(
            "--build",
            help="After a successful release, build distributions locally.",
        ),
    ] = False,
    publish: Annotated[
        bool,
        typer.Option(
            "--publish",
            help=(
                "After a successful release, build and upload to the "
                "configured registry."
            ),
        ),
    ] = False,
    no_changelog: Annotated[
        bool,
        typer.Option(
            "--no-changelog",
            help="Skip automatic changelog updates for this release.",
        ),
    ] = False,
    no_changelog_editor: Annotated[
        bool,
        typer.Option(
            "--no-changelog-editor",
            help=(
                "Do not open an editor on generated changelog entries before "
                "writing."
            ),
        ),
    ] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-V")] = False,
    repo_root: Annotated[
        Path,
        typer.Option("--repo-root", help="Repository root"),
    ] = Path("."),
) -> None:
    """Distlift CLI entry; no subcommand runs default patch release flow.

    Args:
        ctx: Typer invocation context (used to detect bare ``distlift`` runs).
        config_path: Optional extra TOML config path merged after defaults.
        dry_run: When ``True``, plan release without Git writes.
        build: When ``True``, build artifacts after a successful release.
        publish: When ``True``, build and publish after a successful release.
        no_changelog: When ``True``, skip changelog planning for this release.
        no_changelog_editor: When ``True``, skip interactive changelog editing
            before writes.
        verbose: When ``True``, enable verbose logging for this process.
        repo_root: Filesystem path to the repository root directory.
    """
    if ctx.invoked_subcommand is not None:
        return

    configure_logging(verbose)
    application = DistliftApplication()
    extra = [config_path] if config_path else None
    root = repo_root.resolve()
    config = application.load_effective_config(root, extra)

    # Fail fast when merged configuration violates semantic constraints
    try:
        validate_resolved_config(config)
    except Exception as exc:
        typer.echo(f"Configuration error: {exc}", err=True)
        raise typer.Exit(1)

    release_result, build_publish = application.run_default_command(
        root,
        config,
        dry_run=dry_run,
        build=build,
        publish=publish,
        skip_changelog=no_changelog,
        skip_changelog_editor=no_changelog_editor,
    )

    if not release_result.success:
        err_txt = release_result.error or "unknown"
        typer.echo(f"Release failed: {err_txt}", err=True)
        raise typer.Exit(1)

    prefix = "[dry-run] " if dry_run else ""

    tag_line = ", ".join(release_result.tag_names) or "(no tags)"
    typer.echo(f"{prefix}Released: {tag_line}")
    if release_result.commit_sha and not dry_run:
        typer.echo(f"Commit: {release_result.commit_sha}")
    if release_result.pushed_remotes:
        remotes_txt = ", ".join(release_result.pushed_remotes)
        typer.echo(f"Pushed to: {remotes_txt}")

    if build_publish is not None:
        if build_publish.error:
            typer.echo(
                f"Build/publish failed: {build_publish.error}",
                err=True,
            )
            raise typer.Exit(1)

        # One line per project (simple repo or each monorepo package)
        for label, pr in build_publish.projects:
            if not pr.success:
                msg = pr.error or "build or publish failed"
                typer.echo(f"{label}: {msg}", err=True)
                continue

            artifact_names = ", ".join(a.path.name for a in pr.artifacts)

            # Describe build-only vs publish after release
            if publish:
                if artifact_names:
                    typer.echo(f"{prefix}{label}: published {artifact_names}")
                else:
                    typer.echo(f"{prefix}{label}: publish ok")
            elif artifact_names:
                typer.echo(f"{prefix}{label}: built {artifact_names}")
            else:
                typer.echo(f"{prefix}{label}: build ok")

        if not build_publish.success:
            raise typer.Exit(1)


def _resolve_app_config(
    repo_root: Path,
    config_path: Path | None,
    language: str | None,
    remote: list[str] | None,
    default_version: str | None,
    version_format: str | None,
    dry_run: bool,
    verbose: bool,
) -> tuple[DistliftApplication, ResolvedConfig]:
    """Load merged config and apply CLI overrides for release subcommands.

    Args:
        repo_root: Absolute repository root directory path.
        config_path: Optional extra TOML config path merged after defaults.
        language: Optional language string override (e.g. ``python``).
        remote: Optional list of Git remote names replacing configured
            remotes.
        default_version: Optional default version string when no tag exists.
        version_format: Optional ``VersionFormat`` enum value as a string.
        dry_run: Present for a shared helper signature; not read in this
            function.
        verbose: When ``True``, enable verbose logging before config load.

    Returns:
        Application instance and the resolved configuration with CLI layers
        applied via ``attrs.evolve``.
    """
    from distlift.config.models import Language as Lang
    from distlift.config.models import VersionFormat

    configure_logging(verbose)

    application = DistliftApplication()
    extra = [config_path] if config_path else None
    config = application.load_effective_config(repo_root, extra)

    # Apply explicit language override when provided on the CLI
    if language:
        try:
            lang_enum = Lang(language)
        except ValueError:
            typer.echo(f"Unsupported language: {language}", err=True)
            raise typer.Exit(1)
        config = attrs.evolve(config, language=lang_enum)

    if remote:
        config = attrs.evolve(config, remotes=remote)

    if default_version:
        config = attrs.evolve(config, default_version=default_version)

    # Apply explicit version format override when provided on the CLI
    if version_format:
        try:
            fmt = VersionFormat(version_format)
        except ValueError:
            typer.echo(
                f"Unsupported version format: {version_format}", err=True
            )
            raise typer.Exit(1)
        config = attrs.evolve(config, version_format=fmt)

    return application, config


@release_app.command("simple")
def release_simple_command(
    language: Annotated[
        str | None,
        typer.Option(
            "--language", "-l", help="Target language (python, javascript)"
        ),
    ] = None,
    major: Annotated[
        bool, typer.Option("--major", help="Bump major version")
    ] = False,
    minor: Annotated[
        bool, typer.Option("--minor", help="Bump minor version")
    ] = False,
    patch: Annotated[
        bool, typer.Option("--patch", help="Bump patch version")
    ] = False,
    version: Annotated[
        str | None,
        typer.Option("--version", "-v", help="Set explicit version"),
    ] = None,
    config_path: Annotated[
        Path | None, typer.Option("--config", help="Extra config file")
    ] = None,
    remote: Annotated[
        list[str] | None, typer.Option("--remote", help="Push remote(s)")
    ] = None,
    default_version: Annotated[
        str | None, typer.Option("--default-version")
    ] = None,
    version_format: Annotated[
        str | None, typer.Option("--version-format")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Plan only, do not execute")
    ] = False,
    no_changelog_editor: Annotated[
        bool,
        typer.Option(
            "--no-changelog-editor",
            help=(
                "Do not open an editor on generated changelog entries before "
                "writing."
            ),
        ),
    ] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-V")] = False,
    repo_root: Annotated[
        Path, typer.Option("--repo-root", help="Repository root")
    ] = Path("."),
) -> None:
    """Run a simple (single-package) release.

    Args:
        language: Optional target language override.
        major: When ``True``, request a major version bump.
        minor: When ``True``, request a minor version bump.
        patch: When ``True``, request a patch version bump.
        version: Optional explicit version string (mutually exclusive with
            bump flags).
        config_path: Optional extra TOML config path.
        remote: Optional Git remote names for push operations.
        default_version: Optional fallback version when no prior tag exists.
        version_format: Optional version format string override.
        dry_run: When ``True``, plan the release without mutating Git state.
        no_changelog_editor: When ``True``, skip interactive changelog editing.
        verbose: When ``True``, enable verbose logging.
        repo_root: Repository root directory path.
    """
    selectors = sum([major, minor, patch, version is not None])
    if selectors == 0:
        typer.echo(
            "Provide one of --major, --minor, --patch, or --version.", err=True
        )
        raise typer.Exit(1)
    if selectors > 1:
        typer.echo("Provide exactly one version selector.", err=True)
        raise typer.Exit(1)

    bump: BumpKind | None = None
    if major:
        bump = BumpKind.MAJOR
    elif minor:
        bump = BumpKind.MINOR
    elif patch:
        bump = BumpKind.PATCH

    application, config = _resolve_app_config(
        repo_root.resolve(),
        config_path,
        language,
        remote,
        default_version,
        version_format,
        dry_run,
        verbose,
    )

    try:
        validate_resolved_config(config)
    except Exception as exc:
        typer.echo(f"Configuration error: {exc}", err=True)
        raise typer.Exit(1)

    request = SimpleReleaseRequest(
        repo_root=repo_root.resolve(),
        config=config,
        bump=bump,
        explicit_version=version,
        dry_run=dry_run,
        skip_changelog_editor=no_changelog_editor,
    )

    try:
        result = application.run_simple_release(request)
    except Exception as exc:
        typer.echo(f"Release failed: {exc}", err=True)
        raise typer.Exit(1)

    if result.success:
        prefix = "[dry-run] " if dry_run else ""
        typer.echo(f"{prefix}Released: {', '.join(result.tag_names)}")
        if result.commit_sha and not dry_run:
            typer.echo(f"Commit: {result.commit_sha}")
        if result.pushed_remotes:
            typer.echo(f"Pushed to: {', '.join(result.pushed_remotes)}")
    else:
        typer.echo(f"Release failed: {result.error}", err=True)
        raise typer.Exit(1)


@release_app.command("monorepo")
def release_monorepo_command(
    all_changed: Annotated[
        bool,
        typer.Option("--all-changed", help="Release all changed packages"),
    ] = False,
    package: Annotated[
        list[str] | None,
        typer.Option("--package", "-p", help="Specific package name(s)"),
    ] = None,
    default_bump: Annotated[
        str, typer.Option("--default-bump", help="Default bump kind")
    ] = "patch",
    config_path: Annotated[Path | None, typer.Option("--config")] = None,
    remote: Annotated[list[str] | None, typer.Option("--remote")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    no_changelog_editor: Annotated[
        bool,
        typer.Option(
            "--no-changelog-editor",
            help=(
                "Do not open an editor on generated changelog entries before "
                "writing."
            ),
        ),
    ] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-V")] = False,
    repo_root: Annotated[Path, typer.Option("--repo-root")] = Path("."),
) -> None:
    """Run a monorepo (multi-package) release.

    Args:
        all_changed: When ``True``, include every package with changes since
            its last tag.
        package: Optional explicit package names to include in this release.
        default_bump: Default ``BumpKind`` string when a package needs a bump
            without an explicit selector.
        config_path: Optional extra TOML config path.
        remote: Optional Git remote names for push operations.
        dry_run: When ``True``, plan the release without mutating Git state.
        no_changelog_editor: When ``True``, skip interactive changelog editing.
        verbose: When ``True``, enable verbose logging.
        repo_root: Repository root directory path.
    """
    try:
        bump_kind = BumpKind(default_bump)
    except ValueError:
        typer.echo(f"Invalid bump kind: {default_bump}", err=True)
        raise typer.Exit(1)

    application, config = _resolve_app_config(
        repo_root.resolve(),
        config_path,
        None,
        remote,
        None,
        None,
        dry_run,
        verbose,
    )

    try:
        validate_resolved_config(config)
    except Exception as exc:
        typer.echo(f"Configuration error: {exc}", err=True)
        raise typer.Exit(1)

    request = MonorepoReleaseRequest(
        repo_root=repo_root.resolve(),
        config=config,
        default_bump=bump_kind,
        selected_packages=list(package) if package else [],
        all_changed=all_changed,
        dry_run=dry_run,
        skip_changelog_editor=no_changelog_editor,
    )

    try:
        result = application.run_monorepo_release(request)
    except Exception as exc:
        typer.echo(f"Release failed: {exc}", err=True)
        raise typer.Exit(1)

    if result.success:
        prefix = "[dry-run] " if dry_run else ""
        typer.echo(f"{prefix}Released: {', '.join(result.tag_names)}")
    else:
        typer.echo(f"Release failed: {result.error}", err=True)
        raise typer.Exit(1)


@config_app.command("show")
def list_config_command(
    config_path: Annotated[Path | None, typer.Option("--config")] = None,
    repo_root: Annotated[Path, typer.Option("--repo-root")] = Path("."),
) -> None:
    """Print the resolved configuration and per-field source annotations.

    Args:
        config_path: Optional extra TOML config path merged before display.
        repo_root: Repository root directory path.
    """
    application = DistliftApplication()
    extra = [config_path] if config_path else None
    config = application.load_effective_config(repo_root.resolve(), extra)

    typer.echo("Resolved configuration:")
    typer.echo(f"  language        : {config.language}")
    typer.echo(f"  mode            : {config.mode}")
    typer.echo(f"  version_format  : {config.version_format}")
    typer.echo(f"  default_version : {config.default_version}")
    typer.echo(f"  tag_template    : {config.tag_template}")
    typer.echo(f"  version_source  : {config.version_source}")
    typer.echo(f"  remotes         : {config.remotes}")
    typer.echo(f"  manifest_path   : {config.manifest_path}")
    ch = config.changelog
    typer.echo(f"  changelog.enabled : {ch.enabled}")
    typer.echo(f"  changelog.path    : {ch.path}")
    typer.echo(f"  changelog.prompt_editor : {ch.prompt_editor}")
    typer.echo(
        "  changelog.compare_url_template : %s"
        % (ch.compare_url_template or "(auto)")
    )
    hooks = config.hooks
    typer.echo("  hooks (counts per event):")
    typer.echo(f"    tag_pushed        : {len(hooks.tag_pushed)}")
    typer.echo(f"    tag_push_failed   : {len(hooks.tag_push_failed)}")
    typer.echo(f"    release_failed    : {len(hooks.release_failed)}")
    typer.echo(f"    build_succeeded   : {len(hooks.build_succeeded)}")
    typer.echo(f"    build_failed      : {len(hooks.build_failed)}")
    typer.echo(f"    publish_succeeded : {len(hooks.publish_succeeded)}")
    typer.echo(f"    publish_failed    : {len(hooks.publish_failed)}")
    typer.echo("  optional hook env append (after TOML merge), e.g.:")
    for _ev, suf in sorted(
        HOOK_ENV_KEY_SUFFIXES.items(), key=lambda item: item[0]
    ):
        typer.echo(f"    {ENV_PREFIX}HOOKS_{suf}")

    if config.field_sources:
        typer.echo("\nField sources:")
        for field, source in config.field_sources.items():
            typer.echo(f"  {field}: {source}")


@config_app.command("validate")
def validate_config_command(
    config_path: Annotated[Path | None, typer.Option("--config")] = None,
    repo_root: Annotated[Path, typer.Option("--repo-root")] = Path("."),
) -> None:
    """Validate the merged configuration for a repository.

    Args:
        config_path: Optional extra TOML config path merged before validation.
        repo_root: Repository root directory path.
    """
    application = DistliftApplication()
    extra = [config_path] if config_path else None
    config = application.load_effective_config(repo_root.resolve(), extra)
    try:
        validate_resolved_config(config)
        typer.echo("Configuration is valid.")
    except Exception as exc:
        typer.echo(f"Validation failed: {exc}", err=True)
        raise typer.Exit(1)


def _init_config_file(scope: ConfigScope, force: bool) -> None:
    """Create the user or system config file and print a status message.

    Args:
        scope: Whether to target the user-level or system-level path.
        force: When True, overwrite an existing file with the stub.
    """
    try:
        path, created = create_config_file(scope, force=force)
    except ConfigurationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    except OSError as exc:
        typer.echo(
            f"Failed to write {scope.value} config file: {exc}", err=True
        )
        raise typer.Exit(1)

    if created:
        typer.echo(f"Created {scope.value} config: {path}")
    else:
        typer.echo(
            f"{scope.value.capitalize()} config already exists: {path} "
            "(use --force to overwrite)"
        )


def _edit_config_file(scope: ConfigScope, create: bool) -> None:
    """Open the user or system config file in the user's editor.

    Args:
        scope: Whether to target the user-level or system-level path.
        create: When True, seed a stub file when none exists before opening.
    """
    try:
        path, exit_code = open_config_file_in_editor(
            scope, create_if_missing=create
        )
    except ConfigurationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    except OSError as exc:
        typer.echo(
            f"Failed to prepare {scope.value} config file: {exc}", err=True
        )
        raise typer.Exit(1)

    if exit_code != 0:
        typer.echo(
            f"Editor exited with status {exit_code} for {path}", err=True
        )
        raise typer.Exit(exit_code)


@config_app.command("init-user")
def init_user_config_command(
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Overwrite the existing file with the default stub.",
        ),
    ] = False,
) -> None:
    """Create the user-level distlift config file with a commented stub.

    Args:
        force: When True, overwrite the file if it already exists.
    """
    _init_config_file(ConfigScope.USER, force)


@config_app.command("init-system")
def init_system_config_command(
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Overwrite the existing file with the default stub.",
        ),
    ] = False,
) -> None:
    """Create the system-level distlift config file with a commented stub.

    Args:
        force: When True, overwrite the file if it already exists.

    Note:
        On POSIX systems the default system location is ``/etc/distlift/``
        and typically requires elevated privileges. On Windows the default
        is ``%ProgramData%\\distlift\\config.toml``.
    """
    _init_config_file(ConfigScope.SYSTEM, force)


@config_app.command("edit-user")
def edit_user_config_command(
    no_create: Annotated[
        bool,
        typer.Option(
            "--no-create",
            help=(
                "Fail when the file does not exist instead of seeding a "
                "stub before opening the editor."
            ),
        ),
    ] = False,
) -> None:
    """Open the user-level distlift config file in your default editor.

    The editor is resolved from ``GIT_EDITOR``, then ``VISUAL``, then
    ``EDITOR`` (in that order). When the file does not yet exist, a
    commented stub is created first unless ``--no-create`` is given.

    Args:
        no_create: When True, do not create the file if it is missing.
    """
    _edit_config_file(ConfigScope.USER, create=not no_create)


@config_app.command("edit-system")
def edit_system_config_command(
    no_create: Annotated[
        bool,
        typer.Option(
            "--no-create",
            help=(
                "Fail when the file does not exist instead of seeding a "
                "stub before opening the editor."
            ),
        ),
    ] = False,
) -> None:
    """Open the system-level distlift config file in your default editor.

    The editor is resolved from ``GIT_EDITOR``, then ``VISUAL``, then
    ``EDITOR`` (in that order). When the file does not yet exist, a
    commented stub is created first unless ``--no-create`` is given.

    Args:
        no_create: When True, do not create the file if it is missing.

    Note:
        Writing the system file typically requires elevated privileges.
    """
    _edit_config_file(ConfigScope.SYSTEM, create=not no_create)


@plugins_app.command("list")
def list_plugins_command(
    config_path: Annotated[Path | None, typer.Option("--config")] = None,
    repo_root: Annotated[Path, typer.Option("--repo-root")] = Path("."),
    verbose: Annotated[bool, typer.Option("--verbose", "-V")] = False,
) -> None:
    """List plugins discovered and registered for the effective configuration.

    Args:
        config_path: Optional extra TOML config path merged before discovery.
        repo_root: Repository root directory path.
        verbose: When ``True``, enable verbose logging during plugin load.
    """
    configure_logging(verbose)
    application = DistliftApplication()
    extra = [config_path] if config_path else None
    config = application.load_effective_config(repo_root.resolve(), extra)
    registry = application.load_plugins(config)

    entries = registry.list_all()
    if not entries:
        typer.echo("No plugins loaded.")
        return

    typer.echo("Loaded plugins:")
    for entry in entries:
        plugin = entry.plugin
        name = (
            plugin.get_name()
            if isinstance(plugin, DistliftPlugin)
            else repr(plugin)
        )
        override_info = (
            f" (overrides: {entry.overrides})" if entry.overrides else ""
        )
        typer.echo(f"  {name} [{entry.source}]{override_info}")
