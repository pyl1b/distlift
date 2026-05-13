"""Typer subcommands under ``distlift changelog``."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path
from typing import Annotated

import typer

from distlift.app import DistliftApplication
from distlift.changelog.builder import (
    build_changelog_update_plan,
    render_inserted_entry_preview,
    scaffold_initial_changelog_document,
)
from distlift.changelog.models import ChangelogUpdatePlan
from distlift.changelog.writer import write_changelog_document
from distlift.config.models import (
    ManagedPackageConfig,
    ReleaseMode,
    ResolvedConfig,
    VersionFormat,
)
from distlift.config.validators import validate_resolved_config
from distlift.errors import DistliftError
from distlift.logging_utils import configure_logging
from distlift.plugins.registry import PluginRegistry
from distlift.release.simple import prepare_simple_target
from distlift.vcs.git import GitRepository
from distlift.versioning.formatter import format_tag, format_version
from distlift.versioning.parser import parse_version
from distlift.versioning.resolver import find_latest_matching_tag

changelog_app = typer.Typer(
    help="Inspect or update Keep a Changelog Markdown files.",
    no_args_is_help=True,
)


def _bootstrap(
    repo_root: Path,
    config_path: Path | None,
    verbose: bool,
) -> tuple[ResolvedConfig, PluginRegistry, Path]:
    """Load merged configuration, validate it, and build the plugin registry.

    Args:
        repo_root: Repository root passed through config discovery.
        config_path: Optional explicit config file merged last among files.
        verbose: When ``True``, bump logging verbosity before validation.
    """
    configure_logging(verbose)
    application = DistliftApplication()
    extra = [config_path] if config_path else None
    root = repo_root.resolve()
    config = application.load_effective_config(root, extra)

    try:
        validate_resolved_config(config)
    except DistliftError as exc:
        typer.echo(f"Configuration error: {exc}", err=True)
        raise typer.Exit(1)

    registry = application.load_plugins(config)

    return config, registry, root


def _pick_monorepo_package(
    config: ResolvedConfig,
    package: str,
) -> ManagedPackageConfig:
    """Return the managed package definition matching ``package``.

    Args:
        config: Resolved configuration containing ``monorepo.packages``.
        package: Required logical package name from configuration.
    """
    for pkg in config.monorepo.packages:
        if pkg.name == package:
            return pkg

    typer.echo(f"Unknown monorepo package {package!r}", err=True)
    raise typer.Exit(1)


def _resolve_changelog_targets(
    config: ResolvedConfig,
    registry: PluginRegistry,
    repo_root: Path,
    package: str | None,
) -> tuple[Path, str | None, str, VersionFormat, str | None]:
    """Resolve changelog path, Git path filter, tag template, and metadata.

    Args:
        config: Effective merged configuration describing repo mode.
        registry: Plugin registry used when resolving simple-mode targets.
        repo_root: Absolute repository root path.
        package: Optional monorepo package name when ``mode`` is monorepo.
    """
    if config.mode == ReleaseMode.MONOREPO:
        if package is None:
            typer.echo("--package is required in monorepo mode", err=True)
            raise typer.Exit(1)

        pkg = _pick_monorepo_package(config, package)
        template = pkg.tag_template or f"v{{version}}-{pkg.name}"
        fmt = pkg.version_format
        relative_changelog = pkg.changelog_path or config.changelog.path
        changelog_path = (repo_root / pkg.path / relative_changelog).resolve()

        return changelog_path, pkg.path, template, fmt, pkg.name

    if package is not None:
        typer.echo("--package is only valid in monorepo mode", err=True)
        raise typer.Exit(1)

    target = prepare_simple_target(repo_root, config, registry)

    changelog_path = (repo_root / config.changelog.path).resolve()

    return (
        changelog_path,
        None,
        config.tag_template,
        config.version_format,
        target.package_name,
    )


def _build_plan_for_cli(
    *,
    config: ResolvedConfig,
    registry: PluginRegistry,
    repo_root: Path,
    package: str | None,
    version: str,
    since: str | None,
) -> ChangelogUpdatePlan:
    """Construct a changelog update plan for standalone CLI commands.

    Args:
        config: Effective merged configuration for formatting rules.
        registry: Registry used when resolving simple-mode language targets.
        repo_root: Absolute repository root path.
        package: Optional monorepo package selector.
        version: Explicit semantic version text supplied by the caller.
        since: Optional exclusive lower-bound tag overriding history probes.
    """
    changelog_path, pkg_path, template, fmt, pkg_name = (
        _resolve_changelog_targets(config, registry, repo_root, package)
    )

    git = GitRepository(root=repo_root)
    tags = git.get_tags()
    last_tag = since or find_latest_matching_tag(tags, template, fmt, pkg_name)

    parts = parse_version(version, fmt)
    ver_txt = format_version(parts)
    new_tag = format_tag(ver_txt, template, pkg_name)

    return build_changelog_update_plan(
        git,
        changelog_path,
        pkg_path,
        last_tag,
        ver_txt,
        new_tag,
        date.today(),
        config.changelog,
    )


@changelog_app.command("preview")
def changelog_preview_command(
    version: Annotated[
        str,
        typer.Option("--version", "-v", help="Released version label."),
    ],
    package: Annotated[
        str | None,
        typer.Option("--package", "-p", help="Monorepo package name."),
    ] = None,
    since: Annotated[
        str | None,
        typer.Option("--since", help="Lower-bound tag for commit scanning."),
    ] = None,
    config_path: Annotated[Path | None, typer.Option("--config")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-V")] = False,
    repo_root: Annotated[Path, typer.Option("--repo-root")] = Path("."),
) -> None:
    """Print the Markdown fragment that would be inserted for ``version``."""
    config, registry, root = _bootstrap(repo_root, config_path, verbose)

    plan = _build_plan_for_cli(
        config=config,
        registry=registry,
        repo_root=root,
        package=package,
        version=version,
        since=since,
    )

    typer.echo(render_inserted_entry_preview(plan))


@changelog_app.command("update")
def changelog_update_command(
    version: Annotated[
        str,
        typer.Option("--version", "-v", help="Released version label."),
    ],
    package: Annotated[
        str | None,
        typer.Option("--package", "-p", help="Monorepo package name."),
    ] = None,
    since: Annotated[
        str | None,
        typer.Option("--since", help="Lower-bound tag for commit scanning."),
    ] = None,
    config_path: Annotated[Path | None, typer.Option("--config")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-V")] = False,
    repo_root: Annotated[Path, typer.Option("--repo-root")] = Path("."),
) -> None:
    """Rewrite ``CHANGELOG.md`` using the same rules as release integration."""
    config, registry, root = _bootstrap(repo_root, config_path, verbose)

    plan = _build_plan_for_cli(
        config=config,
        registry=registry,
        repo_root=root,
        package=package,
        version=version,
        since=since,
    )

    write_changelog_document(plan.path, plan.new_document)

    typer.echo(f"Updated {plan.path}")


@changelog_app.command("init")
def changelog_init_command(
    package: Annotated[
        str | None,
        typer.Option("--package", "-p", help="Monorepo package name."),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force", help="Backup an existing file then overwrite."
        ),
    ] = False,
    config_path: Annotated[Path | None, typer.Option("--config")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-V")] = False,
    repo_root: Annotated[Path, typer.Option("--repo-root")] = Path("."),
) -> None:
    """Create a minimal Keep a Changelog scaffold when missing."""
    config, registry, root = _bootstrap(repo_root, config_path, verbose)

    changelog_path, _, _, _, _ = _resolve_changelog_targets(
        config,
        registry,
        root,
        package,
    )

    if changelog_path.exists() and not force:
        typer.echo(
            f"Changelog already exists: {changelog_path} "
            "(use --force to overwrite)",
            err=True,
        )
        raise typer.Exit(1)

    if changelog_path.exists() and force:
        backup = changelog_path.with_name(changelog_path.name + ".bak")

        shutil.copy2(changelog_path, backup)

        typer.echo(f"Backed up existing changelog to {backup}")

    document = scaffold_initial_changelog_document(config.changelog)

    write_changelog_document(changelog_path, document)

    typer.echo(f"Initialized {changelog_path}")
