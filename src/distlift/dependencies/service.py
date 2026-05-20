"""Coordinate built-in and plugin dependency autoupdates."""

from __future__ import annotations

from pathlib import Path

from distlift.config.models import (
    DependencyUpdateRule,
    DependencyUpdatesConfig,
    Language,
    ReleaseMode,
)
from distlift.dependencies import javascript, python
from distlift.dependencies.models import (
    DependencyProject,
    DependencyUpdateChange,
    DependencyUpdateRequest,
    DependencyUpdateResult,
    ReleasedProjectVersion,
)
from distlift.dependencies.projects import (
    dependency_projects_from_config,
    filter_receive_enabled_dependency_projects,
    filter_trigger_enabled_released_versions,
    load_external_monorepo_projects,
)
from distlift.logging_utils import get_logger
from distlift.plugins.registry import PluginRegistry

log = get_logger(__name__)

_BUILTIN_UPDATER_NAME = "builtin"


def run_dependency_updates(
    request: DependencyUpdateRequest,
    registry: PluginRegistry,
) -> list[DependencyUpdateResult]:
    """Run all dependency updaters registered for this request.

    Args:
        request: Dependency update inputs including released versions.
        registry: Plugin registry with optional dependency updater plugins.
    """
    results: list[DependencyUpdateResult] = []

    if not request.config.dependency_updates.enabled:
        return results

    builtin = run_builtin_dependency_updates(request)

    if builtin.changes or builtin.warnings:
        results.append(builtin)

    for plugin in registry.get_dependency_updater_plugins():
        plugin_result = plugin.update_dependencies(request)
        results.append(plugin_result)

    return results


def run_builtin_dependency_updates(
    request: DependencyUpdateRequest,
) -> DependencyUpdateResult:
    """Apply built-in dependency update rules and monorepo scanning.

    Args:
        request: Dependency update inputs for this run.
    """
    config = request.config

    if not config.dependency_updates.enabled:
        return DependencyUpdateResult(updater_name=_BUILTIN_UPDATER_NAME)

    released = list(request.released_versions)

    if config.mode == ReleaseMode.MONOREPO:
        packages = config.monorepo.packages
        released = filter_trigger_enabled_released_versions(released, packages)

    if not released:
        return DependencyUpdateResult(updater_name=_BUILTIN_UPDATER_NAME)

    all_changes: list[DependencyUpdateChange] = []
    warnings: list[str] = []
    seen: set[tuple[str, str, str]] = set()

    du = config.dependency_updates
    repo_root = request.repo_root.resolve()

    # Collect projects from current monorepo when enabled
    current_projects: list[DependencyProject] = []

    if du.include_current_monorepo and config.mode == ReleaseMode.MONOREPO:
        from distlift.app import DistliftApplication

        app = DistliftApplication()
        registry = app.load_plugins(config)
        current_projects = dependency_projects_from_config(
            repo_root, config, registry
        )

        if config.mode == ReleaseMode.MONOREPO:
            current_projects = filter_receive_enabled_dependency_projects(
                current_projects, config.monorepo.packages
            )

    # Apply explicit rules first
    matched_packages: set[str] = set()

    for rule in du.rules:
        released_match = matching_released_version(released, rule)

        if released_match is None:
            continue

        matched_packages.add(
            released_match.package_name or released_match.dependency_name
        )
        projects = select_projects_for_rule(current_projects, rule)

        result = update_projects_for_released_versions(
            projects,
            [released_match],
            du,
            rule=rule,
            dry_run=request.dry_run,
            seen=seen,
        )
        all_changes.extend(result.changes)
        warnings.extend(result.warnings)

    # Scan current monorepo for implicit matches when no explicit rule
    if du.include_current_monorepo:
        for rv in released:
            pkg_key = rv.package_name or rv.dependency_name

            if pkg_key in matched_packages:
                continue

            if any(r.package == pkg_key for r in du.rules):
                continue

            result = update_projects_for_released_versions(
                current_projects,
                [rv],
                du,
                rule=None,
                dry_run=request.dry_run,
                seen=seen,
                skip_self=True,
            )
            all_changes.extend(result.changes)
            warnings.extend(result.warnings)

    # External monorepos
    from distlift.app import DistliftApplication

    app = DistliftApplication()

    for ext in du.external_monorepos:
        ext_root = Path(ext.path)

        if not ext_root.is_absolute():
            ext_root = (repo_root / ext.path).resolve()

        config_paths = [Path(p) for p in ext.config_paths]

        try:
            ext_projects = load_external_monorepo_projects(
                repo_root,
                ext_root,
                config_paths,
                app,
            )
        except Exception as exc:
            log.log(
                1,
                "Skipping external monorepo %s: %s",
                ext.path,
                exc,
                exc_info=True,
            )
            warnings.append(
                f"Could not load external monorepo {ext.path}: {exc}"
            )
            continue

        if ext.projects != ["*"]:
            allowed = set(ext.projects)
            ext_projects = [p for p in ext_projects if p.name in allowed]

        if ext_projects and config.mode == ReleaseMode.MONOREPO:
            ext_config = app.load_effective_config(ext_root, config_paths)
            ext_projects = filter_receive_enabled_dependency_projects(
                ext_projects, ext_config.monorepo.packages
            )

        for rv in released:
            result = update_projects_for_released_versions(
                ext_projects,
                [rv],
                du,
                rule=None,
                dry_run=request.dry_run,
                seen=seen,
                skip_self=True,
            )
            all_changes.extend(result.changes)
            warnings.extend(result.warnings)

    return DependencyUpdateResult(
        updater_name=_BUILTIN_UPDATER_NAME,
        changes=all_changes,
        warnings=warnings,
    )


def update_projects_for_released_versions(
    projects: list[DependencyProject],
    released_versions: list[ReleasedProjectVersion],
    du: DependencyUpdatesConfig,
    *,
    rule: DependencyUpdateRule | None,
    dry_run: bool,
    seen: set[tuple[str, str, str]],
    skip_self: bool = False,
) -> DependencyUpdateResult:
    """Update dependency declarations in ``projects`` for released versions.

    Args:
        projects: Dependent projects to inspect.
        released_versions: Released package versions driving updates.
        du: Effective dependency updates configuration.
        rule: Optional explicit rule overriding templates and dependency names.
        dry_run: When True, report changes without writing files.
        seen: Dedup key set mutated in place.
        skip_self: When True, skip updating a project that is also released.
    """
    changes: list[DependencyUpdateChange] = []
    warnings: list[str] = []
    released_names = {
        rv.package_name for rv in released_versions if rv.package_name
    }

    for proj in projects:
        if skip_self and proj.name in released_names:
            continue

        for rv in released_versions:
            dep_name = _dependency_name_for_update(rv, rule)
            template = _version_template_for(rv, du, rule)

            if proj.language == Language.PYTHON:
                pairs = python.update_python_dependency(
                    proj.manifest_path,
                    dep_name,
                    template,
                    rv.version,
                    dry_run=dry_run,
                )
            elif proj.language == Language.JAVASCRIPT:
                pairs = javascript.update_javascript_dependency(
                    proj.manifest_path,
                    dep_name,
                    template,
                    rv.version,
                    dry_run=dry_run,
                )
            else:
                continue

            if not pairs:
                continue

            for old_spec, new_spec in pairs:
                key = (
                    str(proj.manifest_path),
                    dep_name,
                    proj.name,
                )

                if key in seen:
                    continue

                seen.add(key)
                changes.append(
                    DependencyUpdateChange(
                        project_name=proj.name,
                        dependency_name=dep_name,
                        manifest_path=proj.manifest_path,
                        old_specifier=old_spec,
                        new_specifier=new_spec,
                    )
                )

    return DependencyUpdateResult(
        updater_name=_BUILTIN_UPDATER_NAME,
        changes=changes,
        warnings=warnings,
    )


def select_projects_for_rule(
    projects: list[DependencyProject],
    rule: DependencyUpdateRule,
) -> list[DependencyProject]:
    """Filter projects included in an explicit dependency update rule.

    Args:
        projects: All candidate dependent projects.
        rule: Rule with a project name list or ``["*"]``.
    """
    if rule.projects == ["*"]:
        return list(projects)

    allowed = set(rule.projects)

    return [p for p in projects if p.name in allowed]


def matching_released_version(
    released_versions: list[ReleasedProjectVersion],
    rule: DependencyUpdateRule,
) -> ReleasedProjectVersion | None:
    """Return the released version entry matching a rule's package name.

    Args:
        released_versions: Released versions for this run.
        rule: Explicit dependency update rule.
    """
    for rv in released_versions:
        if rv.package_name == rule.package:
            return rv

        if rv.dependency_name == rule.package:
            return rv

    return None


def _dependency_name_for_update(
    rv: ReleasedProjectVersion,
    rule: DependencyUpdateRule | None,
) -> str:
    """Resolve the dependency name to search for in dependent manifests.

    Args:
        rv: Released project version record.
        rule: Optional explicit rule with ``dependency_name`` override.
    """
    if rule is not None and rule.dependency_name:
        return rule.dependency_name

    return rv.dependency_name


def _version_template_for(
    rv: ReleasedProjectVersion,
    du: DependencyUpdatesConfig,
    rule: DependencyUpdateRule | None,
) -> str:
    """Resolve the version specifier template for one released package.

    Args:
        rv: Released project version record.
        du: Global dependency updates configuration.
        rule: Optional explicit rule with ``version_template`` override.
    """
    if rule is not None and rule.version_template:
        return rule.version_template

    if rv.language == Language.JAVASCRIPT:
        return du.javascript_version_template

    return du.python_version_template
