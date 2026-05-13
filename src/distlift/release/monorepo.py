from __future__ import annotations

from pathlib import Path

from distlift.config.models import Language, ManagedPackageConfig, ResolvedConfig
from distlift.errors import UnsupportedLanguageError
from distlift.languages.base import ProjectAdapter
from distlift.monorepo.change_detector import (
    find_changed_packages,
    find_package_last_tag,
)
from distlift.monorepo.discovery import (
    load_managed_packages,
    resolve_package_manifest_path,
)
from distlift.plugins.registry import PluginRegistry
from distlift.release.models import (
    MonorepoReleaseRequest,
    PackageReleasePlan,
    ReleasePlan,
    ReleaseTarget,
)
from distlift.release.planner import plan_monorepo_release
from distlift.vcs.git import GitRepository
from distlift.versioning.resolver import resolve_current_version, resolve_next_version


def _adapter_for(registry: PluginRegistry, language: Language) -> ProjectAdapter:
    from distlift.languages.javascript import (
        JavaScriptProjectAdapter,
        JavaScriptProjectPlugin,
    )
    from distlift.languages.python import PythonProjectAdapter, PythonProjectPlugin

    plugin = registry.get_language_plugin(language.value)
    if isinstance(plugin, PythonProjectPlugin):
        return PythonProjectAdapter()
    if isinstance(plugin, JavaScriptProjectPlugin):
        return JavaScriptProjectAdapter()
    raise UnsupportedLanguageError(f"No adapter for plugin: {plugin.get_name()}")


def discover_managed_targets(
    packages: list[ManagedPackageConfig],
    repo_root: Path,
    config: ResolvedConfig,
    registry: PluginRegistry,
) -> list[ReleaseTarget]:
    targets = []
    for pkg in packages:
        language = pkg.language or config.language
        if language is None:
            raise UnsupportedLanguageError(
                f"Package '{pkg.name}' has no language specified and no default is configured"
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
        (pkg, tgt) for pkg, tgt in zip(packages, targets) if pkg.name in changed_names
    ]


def compute_monorepo_release_plan(
    request: MonorepoReleaseRequest,
    registry: PluginRegistry,
) -> ReleasePlan:
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
            bump=request.default_bump,
            explicit=None,
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

    return plan_monorepo_release(
        pkg_plans, request.config, request.repo_root, request.dry_run
    )
