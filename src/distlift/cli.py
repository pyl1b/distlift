"""Typer-based CLI for distlift (release, config, and plugin commands)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import attrs
import typer

from distlift.app import DistliftApplication
from distlift.cli_changelog import changelog_app
from distlift.config.files import (
    ConfigScope,
    create_config_file,
    create_repo_config_file,
    open_config_file_in_editor,
    open_repo_config_file_in_editor,
)
from distlift.config.models import (
    BumpKind,
    DependencyUpdateRule,
    ExternalMonorepoDependencyUpdateConfig,
    Language,
    ResolvedConfig,
)
from distlift.config.validators import validate_resolved_config
from distlift.constants import ENV_PREFIX, HOOK_ENV_KEY_SUFFIXES
from distlift.dependencies.format import format_dependency_update_summary
from distlift.dependencies.models import ReleasedProjectVersion
from distlift.dependencies.projects import manifest_dependency_name
from distlift.deploy.models import DeployRequest
from distlift.errors import ConfigurationError
from distlift.logging_utils import configure_logging
from distlift.monorepo.discovery import resolve_package_manifest_path
from distlift.plugins.base import DistliftPlugin
from distlift.plugins.scaffold import (
    DependencyUpdaterTemplateOptions,
    create_dependency_updater_plugin,
)
from distlift.publish.models import PublishRunResult
from distlift.release.models import (
    MonorepoReleaseRequest,
    SimpleReleaseRequest,
)

app = typer.Typer(
    name="distlift",
    help=(
        "Release orchestrator for Python and JavaScript packages. "
        "With no subcommand, bumps patch by default; use --major/--minor/"
        "--patch/--version for a different release. Updates manifests, "
        "commits, tags, and pushes. Use --build or --publish to add "
        "distribution steps. Use the ``build`` subcommand to build from "
        "manifest versions only, without releasing."
    ),
)
release_app = typer.Typer(help="Release commands.", no_args_is_help=True)
config_app = typer.Typer(help="Configuration commands.", no_args_is_help=True)
plugins_app = typer.Typer(help="Plugin commands.", no_args_is_help=True)
dependencies_app = typer.Typer(
    help="Dependency autoupdate commands.",
    no_args_is_help=True,
)

app.add_typer(release_app, name="release")
app.add_typer(config_app, name="config")
app.add_typer(plugins_app, name="plugins")
app.add_typer(changelog_app, name="changelog")
app.add_typer(dependencies_app, name="dependencies")


def _echo_dependency_updates(
    results: list,
    *,
    dry_run: bool,
    prefix: str = "",
) -> None:
    """Print dependency autoupdate summary lines when changes exist.

    Args:
        results: Dependency update results from a release or command run.
        dry_run: When True, use dry-run wording in the summary.
        prefix: Optional prefix (for example ``[dry-run] ``).
    """
    summary = format_dependency_update_summary(
        results,
        dry_run=dry_run,
        prefix=prefix,
    )

    if summary:
        typer.echo(summary)
    else:
        typer.echo("No dependencies autoupdated.")


def _parse_released_specs(
    released: list[str],
    config: ResolvedConfig,
    repo_root: Path,
) -> list[ReleasedProjectVersion]:
    """Parse ``package=version`` CLI values into released version records.

    Args:
        released: Repeated ``--released`` option values.
        config: Effective configuration for package lookup.
        repo_root: Repository root for path resolution.
    """
    if not released:
        raise ConfigurationError(
            "At least one --released package=version value is required"
        )

    versions: list[ReleasedProjectVersion] = []
    packages_by_name = {p.name: p for p in config.monorepo.packages}

    for spec in released:
        if "=" not in spec:
            raise ConfigurationError(
                f"Invalid --released value {spec!r}; use package=version"
            )

        pkg_name, version = spec.split("=", 1)
        pkg_name = pkg_name.strip()
        version = version.strip()

        if not pkg_name or not version:
            raise ConfigurationError(
                f"Invalid --released value {spec!r}; use package=version"
            )

        managed = packages_by_name.get(pkg_name)
        language = config.language or Language.PYTHON
        root = repo_root
        manifest = repo_root / "pyproject.toml"

        if managed is not None:
            language = managed.language or language
            root = repo_root / managed.path
            manifest = resolve_package_manifest_path(managed, repo_root)

        dep_name = manifest_dependency_name(manifest, language) or pkg_name

        versions.append(
            ReleasedProjectVersion(
                package_name=pkg_name if managed else None,
                dependency_name=dep_name,
                version=version,
                language=language,
                root=root,
                manifest_path=manifest,
            )
        )

    return versions


def _cli_at_most_one_version_selector(
    major: bool,
    minor: bool,
    patch: bool,
    version: str | None,
    *,
    cmd_label: str,
) -> None:
    """Exit with an error when more than one version selector flag is set.

    Args:
        major: Whether ``--major`` was passed.
        minor: Whether ``--minor`` was passed.
        patch: Whether ``--patch`` was passed.
        version: Value of ``--version`` when set.
        cmd_label: Command name printed in the error message.
    """
    n_selectors = sum([major, minor, patch, version is not None])

    if n_selectors > 1:
        typer.echo(
            f"{cmd_label}: use at most one of --major, --minor, --patch, "
            "or --version.",
            err=True,
        )
        raise typer.Exit(1)


def _bump_kind_from_bool_flags(
    major: bool,
    minor: bool,
    patch: bool,
) -> BumpKind | None:
    """Map mutually exclusive bump flags to a ``BumpKind`` when one is set.

    Args:
        major: Whether ``--major`` was passed.
        minor: Whether ``--minor`` was passed.
        patch: Whether ``--patch`` was passed.
    """
    if major:
        return BumpKind.MAJOR
    if minor:
        return BumpKind.MINOR
    if patch:
        return BumpKind.PATCH

    return None


def _stdin_is_interactive() -> bool:
    """Return True when ``stdin`` looks like an interactive terminal.

    Args:
        None

    Returns:
        Whether ``sys.stdin.isatty()`` is true for the current process.
    """
    return sys.stdin.isatty()


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
    all_changed: Annotated[
        bool,
        typer.Option(
            "--all-changed/--all-packages",
            help=(
                "In monorepo mode, release only packages with commits since "
                "their last tag (default). Use --all-packages to release "
                "every configured package regardless of changes."
            ),
        ),
    ] = True,
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
    verbose: Annotated[bool, typer.Option("--verbose", "-V")] = False,
    repo_root: Annotated[
        Path,
        typer.Option("--repo-root", help="Repository root"),
    ] = Path("."),
) -> None:
    """Distlift CLI entry; no subcommand runs the default release flow.

    Args:
        ctx: Typer invocation context (used to detect bare ``distlift`` runs).
        config_path: Optional extra TOML config path merged after defaults.
        dry_run: When ``True``, plan release without Git writes.
        all_changed: When ``True`` (default), only release monorepo packages
            with commits since their last tag.  Pass ``--all-packages`` to
            release every configured package regardless of changes.
        build: When ``True``, build artifacts after a successful release.
        publish: When ``True``, build and publish after a successful release.
        no_changelog: When ``True``, skip changelog planning for this release.
        no_changelog_editor: When ``True``, skip interactive changelog editing
            before writes.
        major: When ``True``, bump the major version.
        minor: When ``True``, bump the minor version.
        patch: When ``True``, bump the patch version.
        version: Optional explicit version (mutually exclusive with bump flags).
        verbose: When ``True``, enable verbose logging for this process.
        repo_root: Filesystem path to the repository root directory.
    """
    if ctx.invoked_subcommand is not None:
        return

    _cli_at_most_one_version_selector(
        major,
        minor,
        patch,
        version,
        cmd_label="distlift",
    )
    flag_bump = _bump_kind_from_bool_flags(major, minor, patch)
    explicit_ver = version

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
        all_changed=all_changed,
        skip_changelog=no_changelog,
        skip_changelog_editor=no_changelog_editor,
        bump=flag_bump,
        explicit_version=explicit_ver,
    )

    if not release_result.success:
        err_txt = release_result.error or "unknown"
        typer.echo(f"Release failed: {err_txt}", err=True)
        raise typer.Exit(1)

    prefix = "[dry-run] " if dry_run else ""

    tag_line = ", ".join(release_result.tag_names) or "(no tags)"
    typer.echo(f"{prefix}Released: {tag_line}")
    _echo_dependency_updates(
        release_result.dependency_updates,
        dry_run=dry_run,
        prefix=prefix,
    )
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


def _echo_local_build_results(build_result: PublishRunResult) -> None:
    """Print per-package lines for ``distlift build`` and set exit status.

    Args:
        build_result: Aggregated build outcomes from ``run_local_build``.
    """
    if build_result.error:
        typer.echo(f"Build failed: {build_result.error}", err=True)
        raise typer.Exit(1)

    # One line per project (simple repo or each monorepo package)
    for label, pr in build_result.projects:
        if not pr.success:
            msg = pr.error or "build failed"
            typer.echo(f"{label}: {msg}", err=True)
            continue

        artifact_names = ", ".join(a.path.name for a in pr.artifacts)

        if artifact_names:
            typer.echo(f"{label}: built {artifact_names}")
        else:
            typer.echo(f"{label}: build ok")

    if not build_result.success:
        raise typer.Exit(1)


@app.command("build")
def build_command(
    language: Annotated[
        str | None,
        typer.Option(
            "--language", "-l", help="Target language (python, javascript)"
        ),
    ] = None,
    package: Annotated[
        list[str] | None,
        typer.Option(
            "--package",
            "-p",
            help=(
                "Monorepo: build only this package name (repeat for several)."
            ),
        ),
    ] = None,
    config_path: Annotated[
        Path | None, typer.Option("--config", help="Extra config file")
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-V")] = False,
    repo_root: Annotated[
        Path, typer.Option("--repo-root", help="Repository root")
    ] = Path("."),
) -> None:
    """Build local distributions from current manifest versions (no release).

    Does not bump versions, commit, tag, push, or publish. In monorepo mode,
    builds every configured package unless ``--package`` selects a subset.

    Args:
        language: Optional language override for project detection.
        package: Optional monorepo package name(s); ignored in simple mode.
        config_path: Optional extra TOML config path.
        verbose: When ``True``, enable verbose logging.
        repo_root: Repository root directory path.
    """
    application, config = _resolve_app_config(
        repo_root.resolve(),
        config_path,
        language,
        None,
        None,
        None,
        False,
        verbose,
    )

    try:
        validate_resolved_config(config)
    except Exception as exc:
        typer.echo(f"Configuration error: {exc}", err=True)
        raise typer.Exit(1)

    try:
        build_result = application.run_local_build(
            repo_root.resolve(),
            config,
            package_names=package,
        )
    except ConfigurationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    except Exception as exc:
        typer.echo(f"Build failed: {exc}", err=True)
        raise typer.Exit(1)

    _echo_local_build_results(build_result)


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
        _echo_dependency_updates(
            result.dependency_updates,
            dry_run=dry_run,
            prefix=prefix,
        )
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
        typer.Option(
            "--all-changed/--all-packages",
            help=(
                "Release only packages with commits since their last tag "
                "(default). Use --all-packages to release every package."
            ),
        ),
    ] = True,
    package: Annotated[
        list[str] | None,
        typer.Option("--package", "-p", help="Specific package name(s)"),
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
        typer.Option("--version", "-v", help="Set the same explicit version"),
    ] = None,
    default_bump: Annotated[
        str,
        typer.Option(
            "--default-bump",
            help="Bump kind when no --major/--minor/--patch/--version",
        ),
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
        all_changed: When ``True`` (default), include only packages with
            commits since their last tag. Pass ``--all-packages`` to release
            every configured package regardless of changes.
        package: Optional explicit package names to include in this release.
        major: When ``True``, bump major for each selected package.
        minor: When ``True``, bump minor for each selected package.
        patch: When ``True``, bump patch for each selected package.
        version: When set, every selected package uses this exact next
            version (subject to its version format).
        default_bump: ``BumpKind`` string used when none of the bump/version
            flags are passed.
        config_path: Optional extra TOML config path.
        remote: Optional Git remote names for push operations.
        dry_run: When ``True``, plan the release without mutating Git state.
        no_changelog_editor: When ``True``, skip interactive changelog editing.
        verbose: When ``True``, enable verbose logging.
        repo_root: Repository root directory path.
    """
    _cli_at_most_one_version_selector(
        major,
        minor,
        patch,
        version,
        cmd_label="distlift release monorepo",
    )
    flag_bump = _bump_kind_from_bool_flags(major, minor, patch)
    explicit_version = version

    if explicit_version is not None and _stdin_is_interactive():
        msg = (
            f"This will set the next version to {explicit_version} for every "
            "package in this release. Continue?"
        )
        if not typer.confirm(msg, default=False):
            typer.echo("Cancelled.", err=True)
            raise typer.Exit(1)

    if explicit_version is not None:
        bump_kind = BumpKind.PATCH
    elif flag_bump is not None:
        bump_kind = flag_bump
    else:
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
        explicit_version=explicit_version,
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
        _echo_dependency_updates(
            result.dependency_updates,
            dry_run=dry_run,
            prefix=prefix,
        )
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
    typer.echo(f"  editor          : {config.editor or '(unset)'}")
    ch = config.changelog
    typer.echo(f"  changelog.enabled : {ch.enabled}")
    typer.echo(f"  changelog.path    : {ch.path}")
    typer.echo(f"  changelog.prompt_editor : {ch.prompt_editor}")
    typer.echo(
        "  changelog.compare_url_template : %s"
        % (ch.compare_url_template or "(auto)")
    )
    dep = config.deploy
    typer.echo(f"  deploy.tag_prefix      : {dep.tag_prefix}")
    typer.echo(f"  deploy.verify_indexes  : {dep.verify_indexes}")
    du = config.dependency_updates
    typer.echo(f"  dependency_updates.enabled : {du.enabled}")
    typer.echo(
        "  dependency_updates.include_current_monorepo : "
        f"{du.include_current_monorepo}"
    )
    typer.echo(
        "  dependency_updates.python_version_template : "
        f"{du.python_version_template}"
    )
    typer.echo(
        "  dependency_updates.javascript_version_template : "
        f"{du.javascript_version_template}"
    )
    typer.echo(f"  dependency_updates.rules : {len(du.rules)}")
    typer.echo(
        "  dependency_updates.external_monorepos : "
        f"{len(du.external_monorepos)}"
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
    typer.echo(
        f"    dependencies_autoupdated : {len(hooks.dependencies_autoupdated)}"
    )
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


def _init_repo_config_file(repo_root: Path, force: bool) -> None:
    """Create ``distlift.toml`` under the repository root and print status.

    Args:
        repo_root: Repository root directory path.
        force: When True, overwrite an existing ``distlift.toml`` with the stub.
    """
    try:
        path, created = create_repo_config_file(repo_root, force=force)
    except OSError as exc:
        typer.echo(f"Failed to write repo config file: {exc}", err=True)
        raise typer.Exit(1)

    if created:
        typer.echo(f"Created repo config: {path}")
    else:
        typer.echo(
            f"Repo config already exists: {path} "
            "(use --force to overwrite distlift.toml)"
        )


def _edit_repo_config_file(repo_root: Path, create: bool) -> None:
    """Open the repository standalone config in the user's editor.

    Args:
        repo_root: Repository root directory path.
        create: When True, seed ``distlift.toml`` when no standalone file exists.
    """
    try:
        path, exit_code = open_repo_config_file_in_editor(
            repo_root, create_if_missing=create
        )
    except ConfigurationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    except OSError as exc:
        typer.echo(f"Failed to prepare repo config file: {exc}", err=True)
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


@config_app.command("init-repo")
def init_repo_config_command(
    repo_root: Annotated[
        Path,
        typer.Option(
            "--repo-root",
            help="Repository root directory (default: current directory).",
        ),
    ] = Path("."),
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Overwrite distlift.toml if it already exists.",
        ),
    ] = False,
) -> None:
    """Create distlift.toml in the repository with a commented stub.

    Args:
        repo_root: Repository root directory path.
        force: When True, replace an existing ``distlift.toml`` with the stub.
    """
    _init_repo_config_file(repo_root.resolve(), force)


@config_app.command("edit-repo")
def edit_repo_config_command(
    repo_root: Annotated[
        Path,
        typer.Option(
            "--repo-root",
            help="Repository root directory (default: current directory).",
        ),
    ] = Path("."),
    no_create: Annotated[
        bool,
        typer.Option(
            "--no-create",
            help=(
                "Fail when no distlift.toml or .distlift.toml exists instead "
                "of seeding distlift.toml before opening the editor."
            ),
        ),
    ] = False,
) -> None:
    """Open the repository standalone distlift config in your default editor.

    When both ``distlift.toml`` and ``.distlift.toml`` exist, the file that
    wins in merge order (``.distlift.toml``) is opened. The editor is resolved
    from ``GIT_EDITOR``, then ``VISUAL``, then ``EDITOR``, then the merged
    ``editor`` setting (which may come from this repo's TOML or pyproject).
    When no standalone file exists yet, ``distlift.toml`` is created with a
    commented stub first unless ``--no-create`` is given.

    Args:
        repo_root: Repository root directory path.
        no_create: When True, do not create ``distlift.toml`` if it is missing.
    """
    _edit_repo_config_file(repo_root.resolve(), create=not no_create)


@app.command("deploy")
def deploy_command(
    config_path: Annotated[
        Path | None,
        typer.Option("--config", help="Extra config file"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Show the next tag without creating or pushing it.",
        ),
    ] = False,
    remote: Annotated[
        list[str] | None,
        typer.Option("--remote", help="Push remote(s)"),
    ] = None,
    verify_indexes: Annotated[
        bool | None,
        typer.Option(
            "--verify-indexes/--no-verify-indexes",
            help=(
                "Require current manifest version(s) on PyPI/npm before "
                "tagging (overrides deploy.verify_indexes)."
            ),
        ),
    ] = None,
    tag_prefix: Annotated[
        str | None,
        typer.Option(
            "--tag-prefix",
            help="Override deploy.tag_prefix for this run (e.g. release).",
        ),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-V")] = False,
    repo_root: Annotated[
        Path,
        typer.Option("--repo-root", help="Repository root"),
    ] = Path("."),
) -> None:
    """Create and push the next CI marker tag ``{prefix}_{N}`` at HEAD.

    The prefix defaults to ``deploy``; configure it under the ``deploy`` table
    as ``tag_prefix`` or with ``--tag-prefix``. With ``--verify-indexes``,
    refuse to tag until each package version is visible on the index (``pip``
    / ``npm`` use your normal tool config).

    Args:
        config_path: Optional extra TOML config path.
        dry_run: When True, print the planned tag without Git writes.
        remote: Optional Git remote names (replaces configured remotes).
        verify_indexes: Tri-state override for registry checks.
        tag_prefix: Optional one-run prefix for the numbered tag.
        verbose: When True, enable verbose logging.
        repo_root: Repository root directory path.
    """
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

    prefix_opt = tag_prefix.strip() if tag_prefix else None

    if prefix_opt == "":
        typer.echo("--tag-prefix cannot be empty", err=True)
        raise typer.Exit(1)

    eff_deploy = attrs.evolve(
        config.deploy,
        tag_prefix=prefix_opt or config.deploy.tag_prefix,
        verify_indexes=(
            verify_indexes
            if verify_indexes is not None
            else config.deploy.verify_indexes
        ),
    )
    cfg = attrs.evolve(config, deploy=eff_deploy)

    try:
        validate_resolved_config(cfg)
    except Exception as exc:
        typer.echo(f"Configuration error: {exc}", err=True)
        raise typer.Exit(1)

    request = DeployRequest(
        repo_root=repo_root.resolve(),
        config=cfg,
        dry_run=dry_run,
    )

    try:
        result = application.run_deploy(request)
    except Exception as exc:
        typer.echo(f"Deploy failed: {exc}", err=True)
        raise typer.Exit(1)

    if not result.success:
        # Print one line per failed index check only; ``DeployResult.error``
        # repeats the same ``detail`` text and is omitted here on purpose.
        failed_checks = [c for c in result.checks if not c.ok]

        if failed_checks:
            for check in failed_checks:
                typer.echo(
                    "  {} ({}): {}".format(
                        check.label,
                        check.registry_name,
                        check.detail or "failed",
                    ),
                    err=True,
                )
        else:
            typer.echo(result.error or "Deploy failed", err=True)

        raise typer.Exit(1)

    prefix_txt = "[dry-run] " if dry_run else ""

    typer.echo(f"{prefix_txt}Deploy tag: {result.tag_name}")

    if result.pushed_remotes:
        typer.echo("Pushed to: {}".format(", ".join(result.pushed_remotes)))

    for check in result.checks:
        if check.ok:
            typer.echo(
                f"  verified {check.label} {check.registry_name}@{check.version}"
            )


@dependencies_app.command("autoupdate")
def dependencies_autoupdate_command(
    released: Annotated[
        list[str],
        typer.Option(
            "--released",
            help="Released package=version (repeat for multiple packages).",
        ),
    ],
    config_path: Annotated[
        Path | None, typer.Option("--config", help="Extra config file")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview without writing files")
    ] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-V")] = False,
    repo_root: Annotated[Path, typer.Option("--repo-root")] = Path("."),
) -> None:
    """Update dependent project manifests outside the release cycle.

    Args:
        released: One or more ``package=version`` pairs for simulated releases.
        config_path: Optional extra TOML config path merged before the run.
        dry_run: When True, report changes without writing manifests.
        verbose: When True, enable verbose logging.
        repo_root: Repository root directory path.
    """
    configure_logging(verbose)
    application = DistliftApplication()
    extra = [config_path] if config_path else None
    root = repo_root.resolve()
    config = application.load_effective_config(root, extra)

    try:
        validate_resolved_config(config)
        released_versions = _parse_released_specs(released, config, root)
        results = application.run_dependency_autoupdate(
            root,
            config,
            released_versions,
            dry_run=dry_run,
        )
    except Exception as exc:
        typer.echo(f"Dependency autoupdate failed: {exc}", err=True)
        raise typer.Exit(1)

    prefix = "[dry-run] " if dry_run else ""
    _echo_dependency_updates(results, dry_run=dry_run, prefix=prefix)


@plugins_app.command("create-dependency-updater")
def create_dependency_updater_command(
    name: Annotated[str, typer.Argument(help="Plugin project name.")],
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Output directory for the plugin."),
    ] = None,
    watch_package: Annotated[
        list[str],
        typer.Option(
            "--watch-package",
            help="Released package that triggers updates (repeatable).",
        ),
    ] = [],
    project: Annotated[
        list[str],
        typer.Option(
            "--project",
            help="Dependent project to update (default: all).",
        ),
    ] = ["*"],
    monorepo: Annotated[
        list[str],
        typer.Option(
            "--monorepo",
            help="External monorepo path to scan (repeatable).",
        ),
    ] = [],
    python_version_template: Annotated[
        str,
        typer.Option(
            "--python-version-template",
            help="Default Python specifier template.",
        ),
    ] = ">={version}",
    javascript_version_template: Annotated[
        str,
        typer.Option(
            "--javascript-version-template",
            help="Default JavaScript specifier template.",
        ),
    ] = "^{version}",
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite existing files.")
    ] = False,
) -> None:
    """Scaffold a pip-installable dependency updater plugin project.

    Args:
        name: Plugin name used for the Python package and entry point.
        output: Directory to write the plugin project (default: plugins/NAME).
        watch_package: Packages whose releases trigger dependency updates.
        project: Dependent projects to update for each watch package.
        monorepo: External monorepo roots to include in the plugin config.
        python_version_template: Default Python version specifier template.
        javascript_version_template: Default JavaScript version template.
        force: When True, overwrite files that already exist.
    """
    output_dir = output or Path("plugins") / name
    rules: list[DependencyUpdateRule] = []

    if not watch_package:
        watch_package = [name]

    for pkg in watch_package:
        rules.append(
            DependencyUpdateRule(
                package=pkg,
                projects=list(project) if project else ["*"],
            )
        )

    external = [
        ExternalMonorepoDependencyUpdateConfig(path=p, projects=["*"])
        for p in monorepo
    ]

    options = DependencyUpdaterTemplateOptions(
        name=name,
        output_dir=output_dir,
        rules=rules,
        external_monorepos=external,
        force=force,
        python_version_template=python_version_template,
        javascript_version_template=javascript_version_template,
    )

    try:
        written = create_dependency_updater_plugin(options)
    except Exception as exc:
        typer.echo(f"Failed to create plugin: {exc}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Created dependency updater plugin in {output_dir.resolve()}:")
    for path in written:
        typer.echo(f"  {path}")


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
