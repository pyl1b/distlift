from __future__ import annotations

from pathlib import Path
from typing import Annotated

import attrs
import typer

from distlift.app import DistliftApplication
from distlift.config.models import BumpKind, ResolvedConfig
from distlift.config.validators import validate_resolved_config
from distlift.logging_utils import configure_logging
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
    verbose: Annotated[bool, typer.Option("--verbose", "-V")] = False,
    repo_root: Annotated[
        Path,
        typer.Option("--repo-root", help="Repository root"),
    ] = Path("."),
) -> None:
    """Distlift CLI entry; no subcommand runs a patch release and optional distro steps."""
    if ctx.invoked_subcommand is not None:
        return

    configure_logging(verbose)
    application = DistliftApplication()
    extra = [config_path] if config_path else None
    root = repo_root.resolve()
    config = application.load_effective_config(root, extra)

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
    from distlift.config.models import Language as Lang
    from distlift.config.models import VersionFormat

    configure_logging(verbose)

    application = DistliftApplication()
    extra = [config_path] if config_path else None
    config = application.load_effective_config(repo_root, extra)

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
    verbose: Annotated[bool, typer.Option("--verbose", "-V")] = False,
    repo_root: Annotated[
        Path, typer.Option("--repo-root", help="Repository root")
    ] = Path("."),
) -> None:
    """Run a simple (single-package) release."""
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
    verbose: Annotated[bool, typer.Option("--verbose", "-V")] = False,
    repo_root: Annotated[Path, typer.Option("--repo-root")] = Path("."),
) -> None:
    """Run a monorepo (multi-package) release."""
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
    """Show the resolved configuration and the source of each field."""
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

    if config.field_sources:
        typer.echo("\nField sources:")
        for field, source in config.field_sources.items():
            typer.echo(f"  {field}: {source}")


@config_app.command("validate")
def validate_config_command(
    config_path: Annotated[Path | None, typer.Option("--config")] = None,
    repo_root: Annotated[Path, typer.Option("--repo-root")] = Path("."),
) -> None:
    """Validate the resolved configuration."""
    application = DistliftApplication()
    extra = [config_path] if config_path else None
    config = application.load_effective_config(repo_root.resolve(), extra)
    try:
        validate_resolved_config(config)
        typer.echo("Configuration is valid.")
    except Exception as exc:
        typer.echo(f"Validation failed: {exc}", err=True)
        raise typer.Exit(1)


@plugins_app.command("list")
def list_plugins_command(
    config_path: Annotated[Path | None, typer.Option("--config")] = None,
    repo_root: Annotated[Path, typer.Option("--repo-root")] = Path("."),
    verbose: Annotated[bool, typer.Option("--verbose", "-V")] = False,
) -> None:
    """List all discovered and loaded plugins."""
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
            plugin.get_name() if hasattr(plugin, "get_name") else repr(plugin)
        )  # type: ignore[union-attr]
        override_info = (
            f" (overrides: {entry.overrides})" if entry.overrides else ""
        )
        typer.echo(f"  {name} [{entry.source}]{override_info}")
