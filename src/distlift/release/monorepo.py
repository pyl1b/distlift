from __future__ import annotations

from pathlib import Path

import attrs

from distlift.config.models import (
    Language,
    ManagedPackageConfig,
    ResolvedConfig,
)
from distlift.errors import UnsupportedLanguageError
from distlift.languages.base import ProjectAdapter
from distlift.monorepo.change_detector import (
    find_changed_packages,
)
from distlift.monorepo.discovery import (
    load_managed_packages,
    resolve_package_manifest_path,
)
from distlift.plugins.registry import PluginRegistry
from distlift.release.changelog_extra import finalize_plan_with_changelog
from distlift.release.models import (
    MonorepoReleaseRequest,
    PackageReleasePlan,
    ReleasePlan,
    ReleaseTarget,
)
from distlift.release.planner import plan_monorepo_release
from distlift.vcs.git import GitRepository
from distlift.versioning.resolver import (
    resolve_current_version,
    resolve_next_version,
)


def _adapter_for(
    registry: PluginRegistry, language: Language
) -> ProjectAdapter:
    """Return a project adapter for the registered language plugin.

    Args:
        registry: Active plugin registry.
        language: Language enum member to resolve.
    """
    from distlift.languages.javascript import (
        JavaScriptProjectAdapter,
        JavaScriptProjectPlugin,
    )
    from distlift.languages.python import (
        PythonProjectAdapter,
        PythonProjectPlugin,
    )

    plugin = registry.get_language_plugin(language.value)
    if isinstance(plugin, PythonProjectPlugin):
        return PythonProjectAdapter()
    if isinstance(plugin, JavaScriptProjectPlugin):
        return JavaScriptProjectAdapter()
    raise UnsupportedLanguageError(
        f"No adapter for plugin: {plugin.get_name()}"
    )


def discover_managed_targets(
    packages: list[ManagedPackageConfig],
    repo_root: Path,
    config: ResolvedConfig,
    registry: PluginRegistry,
) -> list[ReleaseTarget]:
    """Build a ReleaseTarget for each managed package declaration.

    Args:
        packages: Monorepo package entries from configuration.
        repo_root: Repository root used to resolve paths.
        config: Resolved configuration for default language fallbacks.
        registry: Plugin registry (reserved for future per-package wiring).
    """
    targets = []
    for pkg in packages:
        language = pkg.language or config.language
        if language is None:
            raise UnsupportedLanguageError(
                f"Package {pkg.name!r} has no language configured "
                "and no repository default exists"
            )
        manifest = resolve_package_manifest_path(pkg, repo_root)
        targets.append(
            ReleaseTarget(
                language=language,
                root=repo_root / pkg.path,
                manifest_path=manifest,
                version_source=pkg.version_source,
                package_name=pkg.name,
            )
        )
    return targets


def select_changed_targets(
    packages: list[ManagedPackageConfig],
    targets: list[ReleaseTarget],
    tags: list[str],
    git: GitRepository,
    selected_names: list[str] | None,
    all_changed: bool,
) -> list[tuple[ManagedPackageConfig, ReleaseTarget]]:
    """Pair managed packages with targets that should be part of this release.

    Args:
        packages: Declared managed packages in configuration order.
        targets: Parallel list of release targets for those packages.
        tags: Existing tag names used for change detection.
        git: Repository handle for diff-based change detection.
        selected_names: Optional filter of package names to include.
        all_changed: If True, only packages with commits since their tag.
    """
    if all_changed:
        changed_pkgs = find_changed_packages(
            packages, tags, git, selected_names or None
        )
    else:
        if selected_names:
            changed_pkgs = [p for p in packages if p.name in selected_names]
        else:
            changed_pkgs = list(packages)

    changed_names = {p.name for p in changed_pkgs}
    return [
        (pkg, tgt)
        for pkg, tgt in zip(packages, targets)
        if pkg.name in changed_names
    ]


def compute_monorepo_release_plan(
    request: MonorepoReleaseRequest,
    registry: PluginRegistry,
) -> ReleasePlan:
    """Compute a monorepo release plan for changed or selected packages.

    Args:
        request: Monorepo request with repo root, bumps, and filters.
        registry: Plugin registry used for adapters and dynamic-version checks.
    """
    git = GitRepository(root=request.repo_root)
    git.ensure_clean_worktree()

    packages = load_managed_packages(request.config)
    targets = discover_managed_targets(
        packages, request.repo_root, request.config, registry
    )
    tags = git.get_tags()

    selected_names = request.selected_packages or None
    pairs = select_changed_targets(
        packages, targets, tags, git, selected_names, request.all_changed
    )

    pkg_plans: list[PackageReleasePlan] = []

    # Resolve next version and manifest policy per selected package pair
    for pkg, tgt in pairs:
        template = pkg.tag_template or f"v{{version}}-{pkg.name}"
        fmt = pkg.version_format

        current = resolve_current_version(
            tags=tags,
            template=template,
            fmt=fmt,
            default_version=pkg.default_version,
            package_name=pkg.name,
        )
        resolved = resolve_next_version(
            current=current,
            bump=request.default_bump
            if request.explicit_version is None
            else None,
            explicit=request.explicit_version,
            fmt=fmt,
            template=template,
            package_name=pkg.name,
        )

        adapter = _adapter_for(registry, tgt.language)
        update_manifest = not adapter.is_dynamic_version(tgt)

        pkg_plans.append(
            PackageReleasePlan(
                target=tgt,
                resolved_version=resolved,
                update_manifest=update_manifest,
            )
        )

    plan = plan_monorepo_release(
        pkg_plans, request.config, request.repo_root, request.dry_run
    )

    plan = finalize_plan_with_changelog(
        plan,
        git_repo=git,
        tags=tags,
        config=request.config,
        skip_changelog=request.skip_changelog,
    )

    return attrs.evolve(
        plan,
        changelog_prompt_editor=request.config.changelog.prompt_editor,
        skip_changelog_editor=request.skip_changelog_editor,
        editor_command=request.config.editor,
    )
