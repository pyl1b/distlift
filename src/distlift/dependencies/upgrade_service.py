"""Orchestrate interactive third-party dependency upgrades."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from distlift.dependencies.projects import (
    dependency_projects_from_config,
    filter_receive_enabled_dependency_projects,
)
from distlift.dependencies.registry_resolver import (
    RegistryResolver,
    enrich_dependency_metadata,
)
from distlift.dependencies.upgrade_models import (
    DependencyUpgradePlan,
    DependencyUpgradeResult,
    SourceUpgradePlan,
    SourceUpgradeResult,
)
from distlift.dependencies.version_cycle import filter_upgradable_choices
from distlift.errors import DependencyUpgradeError
from distlift.logging_utils import get_logger
from distlift.monorepo.discovery import load_managed_packages
from distlift.package_managers.detection import detect_package_source
from distlift.plugins.registry import PluginRegistry
from distlift.terminal.selector_backend import (
    SelectorBackend,
    SelectorCancelledError,
)

if TYPE_CHECKING:
    from distlift.config.models import ResolvedConfig

log = get_logger(__name__)


def discover_upgrade_sources(
    repo_root: Path,
    config: ResolvedConfig,
    registry: PluginRegistry,
    *,
    project_filter: list[str] | None = None,
    manager_overrides: dict[str, str] | None = None,
) -> list:
    """Discover package sources eligible for interactive upgrades.

    Args:
        repo_root: Repository root directory.
        config: Effective merged configuration.
        registry: Plugin registry with package manager plugins.
        project_filter: Optional project name allow-list.
        manager_overrides: Optional per-project manager overrides.

    Returns:
        Detected package sources sorted by project name.
    """
    from distlift.dependencies.upgrade_models import PackageSource

    projects = dependency_projects_from_config(repo_root, config, registry)

    if config.dependency_upgrades.respect_receive_enabled:
        packages = load_managed_packages(config)
        projects = filter_receive_enabled_dependency_projects(
            projects,
            packages,
        )

    if project_filter:
        allowed = {name.strip() for name in project_filter if name.strip()}
        projects = [proj for proj in projects if proj.name in allowed]

    sources: list[PackageSource] = []

    for project in sorted(projects, key=lambda item: item.name.lower()):
        source = detect_package_source(
            project,
            registry,
            manager_overrides=manager_overrides,
            upgrades_config=config.dependency_upgrades,
        )
        sources.append(source)

    return sources


def build_source_choices(
    source,
    registry: PluginRegistry,
    config: ResolvedConfig,
):
    """Build registry-enriched dependency choices for one source.

    Args:
        source: Package source to inspect.
        registry: Plugin registry with package manager plugins.
        config: Effective merged configuration.
    """
    plugin = registry.get_package_manager_plugin(source.manager_name)
    dependencies = plugin.list_dependencies(source)
    dependencies = enrich_dependency_metadata(
        plugin,
        source,
        dependencies,
    )
    resolver = RegistryResolver(
        plugin,
        timeout_seconds=config.dependency_upgrades.registry_timeout_seconds,
        max_workers=config.dependency_upgrades.registry_max_workers,
    )
    return filter_upgradable_choices(
        resolver.build_choices(source, dependencies)
    )


def build_upgrade_plan(
    repo_root: Path,
    sources_with_selections: list[tuple],
    *,
    dry_run: bool,
    registry: PluginRegistry,
    config: ResolvedConfig,
) -> DependencyUpgradePlan:
    """Build an immutable upgrade plan from approved selections.

    Args:
        repo_root: Repository root directory.
        sources_with_selections: Pairs of package source and user selections.
        dry_run: Whether the plan will execute as a preview only.
        registry: Plugin registry with package manager plugins.
        config: Effective merged configuration.
    """
    source_plans: list[SourceUpgradePlan] = []
    seen_locations: set[str] = set()

    for source, selections in sources_with_selections:
        for selection in selections:
            if selection.target_version is None:
                continue

            key = selection.dependency.location_key

            if key in seen_locations:
                raise DependencyUpgradeError(
                    f"Duplicate selection for dependency location {key}"
                )

            seen_locations.add(key)

        plugin = registry.get_package_manager_plugin(source.manager_name)
        active = [
            selection
            for selection in selections
            if selection.target_version is not None
        ]
        changes = plugin.apply_manifest_updates(
            source,
            active,
            config,
            dry_run=True,
        )
        source_plans.append(
            SourceUpgradePlan(
                source=source,
                selections=tuple(selections),
                manifest_path=source.project.manifest_path,
                planned_changes=tuple(changes),
            )
        )

    return DependencyUpgradePlan(
        repo_root=repo_root,
        sources=tuple(source_plans),
        dry_run=dry_run,
        install_packages=config.dependency_upgrades.install_packages,
    )


def execute_upgrade_plan(
    plan: DependencyUpgradePlan,
    registry: PluginRegistry,
    config: ResolvedConfig,
) -> DependencyUpgradeResult:
    """Execute one dependency upgrade plan transactionally per source.

    Args:
        plan: Immutable upgrade plan to execute.
        registry: Plugin registry with package manager plugins.
        config: Effective merged configuration.
    """
    results: list[SourceUpgradeResult] = []

    for source_plan in plan.sources:
        active = [
            selection
            for selection in source_plan.selections
            if selection.target_version is not None
        ]

        if not active:
            results.append(
                SourceUpgradeResult(
                    source_name=source_plan.source.project.name
                )
            )
            continue

        plugin = registry.get_package_manager_plugin(
            source_plan.source.manager_name
        )
        snapshots = _snapshot_files(source_plan)

        try:
            changes = plugin.apply_manifest_updates(
                source_plan.source,
                active,
                config,
                dry_run=plan.dry_run,
            )

            lock_paths: list[Path] = []
            packages_installed: list[str] = []

            if changes and not plan.dry_run:
                if config.dependency_upgrades.install_packages:
                    install_results = plugin.install_packages(
                        source_plan.source,
                        active,
                        config,
                        dry_run=False,
                        timeout_seconds=config.dependency_upgrades.install_timeout_seconds,
                    )
                    packages_installed = [
                        " ".join(result.command) for result in install_results
                    ]
                else:
                    lock_paths = plugin.refresh_lock_files(
                        source_plan.source,
                        dry_run=False,
                        timeout_seconds=config.dependency_upgrades.lock_refresh_timeout_seconds,
                    )

            if not plan.dry_run:
                errors = plugin.verify_upgrades(
                    source_plan.source,
                    active,
                    config,
                )

                if errors:
                    raise DependencyUpgradeError("; ".join(errors))

            results.append(
                SourceUpgradeResult(
                    source_name=source_plan.source.project.name,
                    manifest_changes=changes,
                    lock_files_updated=lock_paths,
                    packages_installed=packages_installed,
                )
            )
        except Exception as exc:
            if not plan.dry_run:
                _restore_snapshots(snapshots)

                if config.dependency_upgrades.install_packages:
                    warnings_msg = (
                        "Manifest files were restored, but the environment "
                        "may still contain partially installed packages"
                    )
                    log.log(1, "%s", warnings_msg)

            log.log(
                1,
                "Upgrade failed for source %s: %s",
                source_plan.source.project.name,
                exc,
                exc_info=True,
            )

            results.append(
                SourceUpgradeResult(
                    source_name=source_plan.source.project.name,
                    rolled_back=not plan.dry_run,
                    warnings=(
                        [
                            "Manifest files were restored, but the environment "
                            "may still contain partially installed packages"
                        ]
                        if not plan.dry_run
                        and config.dependency_upgrades.install_packages
                        else []
                    ),
                )
            )

            return DependencyUpgradeResult(
                success=False,
                source_results=results,
                error=str(exc),
            )

    return DependencyUpgradeResult(success=True, source_results=results)


def run_interactive_upgrade_session(
    repo_root: Path,
    config: ResolvedConfig,
    registry: PluginRegistry,
    *,
    dry_run: bool,
    selector: SelectorBackend,
    project_filter: list[str] | None = None,
    manager_overrides: dict[str, str] | None = None,
    confirm_callback=None,
) -> DependencyUpgradeResult:
    """Run discovery, selection, confirmation, and execution.

    Args:
        repo_root: Repository root directory.
        config: Effective merged configuration.
        registry: Plugin registry with package manager plugins.
        dry_run: Whether to preview without writing files.
        selector: UI backend used for per-source selection.
        project_filter: Optional project name allow-list.
        manager_overrides: Optional per-project manager overrides.
        confirm_callback: Optional callable returning bool for final confirm.

    Raises:
        SelectorCancelledError: When the user cancels during selection.
        DependencyUpgradeError: When upgrade configuration or execution fails.
    """
    if not config.dependency_upgrades.enabled:
        raise DependencyUpgradeError(
            "dependency_upgrades.enabled is false; enable [dependency_upgrades] "
            "to run distlift deps upgrade"
        )

    sources = discover_upgrade_sources(
        repo_root,
        config,
        registry,
        project_filter=project_filter,
        manager_overrides=manager_overrides,
    )

    if not sources:
        raise DependencyUpgradeError("No package sources found to upgrade")

    approved: list[tuple] = []

    for source in sources:
        choices = build_source_choices(source, registry, config)

        if not choices:
            log.log(
                1,
                "No upgradable dependencies for source %s",
                source.project.name,
            )
            approved.append((source, []))
            continue

        selections = selector.select(source, choices)
        approved.append((source, selections))

    plan = build_upgrade_plan(
        repo_root,
        approved,
        dry_run=dry_run,
        registry=registry,
        config=config,
    )

    if confirm_callback is not None:
        if not confirm_callback(plan):
            raise SelectorCancelledError("cancelled")

    return execute_upgrade_plan(plan, registry, config)


def format_plan_summary(plan: DependencyUpgradePlan) -> str:
    """Render a human-readable summary for final confirmation.

    Args:
        plan: Upgrade plan to summarize.
    """
    lines: list[str] = []
    total = 0

    for source_plan in plan.sources:
        lines.append(f"  {source_plan.source.project.name}:")

        for selection in source_plan.selections:
            if selection.target_version is None:
                lines.append(f"    {selection.dependency.name} (skip)")
                continue

            total += 1
            lines.append(
                "    {} {} -> {} ({})".format(
                    selection.dependency.name,
                    selection.dependency.installed_version
                    or selection.dependency.resolved_version
                    or selection.dependency.constraint,
                    selection.target_version,
                    selection.dependency.group,
                )
            )

        lock_files = source_plan.source.lock_files

        if not plan.install_packages and lock_files:
            lines.append(
                "    lock files: {}".format(
                    ", ".join(str(path.name) for path in lock_files)
                )
            )

    if plan.install_packages and not plan.dry_run:
        lines.append("  Environment install: enabled")

    prefix = "Planned upgrades"
    if plan.dry_run:
        prefix = "Planned upgrades (dry-run)"

    header = (
        f"{prefix} ({total} dependencies across {len(plan.sources)} sources):"
    )
    return "\n".join([header, *lines])


def _snapshot_files(source_plan: SourceUpgradePlan) -> dict[Path, str]:
    """Snapshot manifest and lock files before mutation.

    Args:
        source_plan: Source plan whose files should be snapshotted.
    """
    paths = [source_plan.manifest_path, *source_plan.source.lock_files]
    snapshots: dict[Path, str] = {}

    for path in paths:
        if path.is_file():
            snapshots[path] = path.read_text(encoding="utf-8")

    return snapshots


def _restore_snapshots(snapshots: dict[Path, str]) -> None:
    """Restore files from an earlier snapshot map.

    Args:
        snapshots: Mapping of file path to original text content.
    """
    for path, content in snapshots.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

        log.log(1, "Restored snapshot for %s", path)
